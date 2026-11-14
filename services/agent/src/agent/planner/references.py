"""Whole-value bindings from validated earlier outputs; never expression evaluation."""

from __future__ import annotations

import re
from collections.abc import Iterator
from copy import deepcopy
from typing import Any

from jsonschema import Draft202012Validator, validators
from pydantic import BaseModel
from referencing import Registry

from agent.contracts.plan import Plan
from agent.tools.base import ToolRegistry

_REFERENCE = re.compile(r"\$step([1-9][0-9]{0,5})\.([A-Za-z][A-Za-z0-9_]{0,127})\Z")


class ReferenceError(ValueError):
    def __init__(self) -> None:
        super().__init__("Invalid step reference")


def parse_reference(value: str) -> tuple[int, str] | None:
    if "$step" not in value:
        return None
    match = _REFERENCE.fullmatch(value)
    if match is None:
        raise ReferenceError()
    return int(match[1]), match[2]


def references(value: Any) -> Iterator[tuple[int, str]]:
    if isinstance(value, str):
        found = parse_reference(value)
        if found is not None:
            yield found
    elif isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or "$step" in key:
                raise ReferenceError()
            yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def validate_bindings(
    args: dict[str, Any], *, position: int, plan: Plan, registry: ToolRegistry
) -> bool:
    found = tuple(references(args))
    for number, name in found:
        if number >= position:
            raise ReferenceError()
        producer = registry.spec(plan.steps[number - 1].tool).output_model
        field = producer.model_fields.get(name)
        if field is None or field.exclude is True:
            raise ReferenceError()
    return bool(found)


def _guard(original: Any, keyword: str) -> Any:
    def validate(validator: Any, constraint: Any, instance: Any, schema: Any) -> Iterator[Any]:
        if isinstance(instance, str) and parse_reference(instance) is not None:
            return
        # These constraints cannot be decided from a partially unknown instance.
        # They remain mandatory in full Pydantic validation after resolution.
        if keyword in {
            "oneOf",
            "not",
            "if",
            "contains",
            "unevaluatedProperties",
            "unevaluatedItems",
        } and any(references(instance)):
            return
        yield from original(validator, constraint, instance, schema)

    return validate


# The upstream factory lacks a typed signature; validator callbacks are typed above.
_TemplateValidator = validators.extend(  # type: ignore[no-untyped-call]
    Draft202012Validator,
    {name: _guard(check, name) for name, check in Draft202012Validator.VALIDATORS.items()},
)


def _closed_schema(node: Any) -> None:
    if isinstance(node, dict):
        for name in ("$ref", "$dynamicRef", "$recursiveRef"):
            if name in node and (not isinstance(node[name], str) or not node[name].startswith("#")):
                raise ReferenceError()  # No schema retrieval/network access.
        if "properties" in node:
            node["additionalProperties"] = False
        for value in node.values():
            _closed_schema(value)
    elif isinstance(node, list):
        for value in node:
            _closed_schema(value)


def validate_template(model: type[BaseModel], args: dict[str, Any]) -> None:
    """Check known structure/literals; unresolved values and cross-field checks defer."""
    try:
        schema = model.model_json_schema()
        _closed_schema(schema)
        # Empty explicit registry disables external retrieval, including local files.
        if (
            next(_TemplateValidator(schema, registry=Registry()).iter_errors(args), None)
            is not None
        ):
            raise ReferenceError()
    except Exception:  # noqa: BLE001 - schema diagnostics may contain private argument values
        raise ReferenceError() from None


def resolve_args(args: dict[str, Any], outputs: list[dict[str, Any]]) -> dict[str, Any]:
    def resolve(value: Any) -> Any:
        if isinstance(value, str):
            ref = parse_reference(value)
            if ref is not None:
                number, name = ref
                if number > len(outputs) or name not in outputs[number - 1]:
                    raise ReferenceError()
                # Copy once. Returned strings/containers are DATA, not more bindings.
                return deepcopy(outputs[number - 1][name])
        if isinstance(value, dict):
            return {key: resolve(child) for key, child in value.items()}
        if isinstance(value, list):
            return [resolve(child) for child in value]
        return deepcopy(value)

    resolved = resolve(args)
    assert isinstance(resolved, dict)
    return resolved
