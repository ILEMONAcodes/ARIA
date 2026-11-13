"""C1 validation has no model, network or execution dependencies."""

import json

import pytest
from pydantic import BaseModel

from agent.contracts.plan import Plan
from agent.fakes.tools import FakeTool
from agent.planner import PlanValidationError, validate_plan
from agent.tools import ToolRegistry


@pytest.fixture
def registry():
    class NeverRun(FakeTool):
        def run(self, args):
            raise AssertionError("Validation must not execute a tool")

        def dry_run(self, args):
            raise AssertionError("Validation must not invoke dry-run code")

    result = ToolRegistry()
    result.register(NeverRun())
    return result


def payload(**changes):
    return {
        "intent": "echo",
        "confidence": 0.9,
        "steps": [{"tool": "test.echo", "args": {"text": "fictional request"}}],
        **changes,
    }


def test_registered_plan_validates_offline_without_running_any_tool(
    registry, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    raw = payload()
    for value in (raw, json.dumps(raw), Plan.model_validate(raw)):
        review = validate_plan(value, registry)
        assert not review.requires_clarification
        assert review.plan.steps[0].args == {"text": "fictional request"}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "change",
    [
        {"confidence": "0.9"},
        {"confidence": True},
        {"confidence": float("nan")},
        {"needs_network": "false"},
        {"needs_confirmation": 0},
        {"unknown": "secret"},
        {"intent": " "},
        {"missing": [" "]},
        {"slots": {"amount": float("inf")}},
        {"steps": [{"tool": "test.echo", "args": {"text": "x"}, "run": True}]},
        {"steps": [{"tool": "test.echo", "args": {"text": 123}}]},
        {"steps": [{"tool": "test.echo", "args": {"text": "x", "recipient": "secret"}}]},
        {"steps": [{"tool": "test.echo", "args": {}}]},
        {"steps": [{"tool": "shell.exec", "args": {"command": "secret"}}]},
        {"steps": [{"tool": "test.echo", "args": {"text": "$step1.text"}}]},
    ],
)
def test_invalid_plan_fails_without_exposing_values(registry, change):
    with pytest.raises(PlanValidationError) as error:
        validate_plan(payload(**change), registry)
    assert str(error.value) == "Invalid plan"
    assert error.value.__cause__ is None


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        "null",
        "not json",
        "```json\n{}\n```",
        '{"intent":"secret","intent":"echo","confidence":0.9}',
        '{"intent":"echo","confidence":0.9,"slots":{"x":1,"x":2}}',
        '{"intent":"echo","confidence":NaN}',
    ],
)
def test_invalid_json_and_duplicate_keys_are_rejected(registry, raw):
    with pytest.raises(PlanValidationError):
        validate_plan(raw, registry)


@pytest.mark.parametrize("confidence,expected", [(0.59, True), (0.6, False), (0.9, False)])
def test_low_confidence_requires_clarification(registry, confidence, expected):
    assert (
        validate_plan(payload(confidence=confidence), registry).requires_clarification is expected
    )


def test_missing_slots_are_exposed_one_at_a_time_and_empty_steps_do_not_act(registry):
    review = validate_plan(payload(missing=["recipient", "date"], steps=[]), registry)
    assert review.requires_clarification
    assert review.first_missing == "recipient"
    assert validate_plan(payload(steps=[]), registry).requires_clarification
    assert validate_plan(payload(), registry).first_missing is None


def test_plan_snapshot_is_independent_of_caller_mutations(registry):
    original = Plan.model_validate(payload())
    review = validate_plan(original, registry)
    original.steps[0].args["text"] = "changed"
    assert review.plan.steps[0].args["text"] == "fictional request"
    assert "fictional request" not in repr(review)


@pytest.mark.parametrize("risk", ["local_write", "external_send", "destructive"])
def test_plan_cannot_understate_registered_tool_risk(registry, risk):
    class Risky(FakeTool):
        name = "test.risky"

    Risky.risk = risk
    registry.register(Risky())
    steps = [{"tool": "test.risky", "args": {"text": "fictional"}}]
    with pytest.raises(PlanValidationError):
        validate_plan(payload(steps=steps), registry)
    with pytest.raises(PlanValidationError):
        validate_plan(payload(steps=steps, risk=risk, needs_confirmation=False), registry)
    review = validate_plan(payload(steps=steps, risk=risk, needs_confirmation=True), registry)
    assert review.plan.needs_confirmation


def test_multi_step_policy_uses_highest_risk_and_any_network_requirement(registry):
    class Send(FakeTool):
        name = "test.send"
        risk = "external_send"
        needs_network = True

    registry.register(Send())
    steps = payload()["steps"] + [{"tool": "test.send", "args": {"text": "fictional"}}]
    good = payload(steps=steps, risk="external_send", needs_confirmation=True, needs_network=True)
    assert not validate_plan(good, registry).requires_clarification
    with pytest.raises(PlanValidationError):
        validate_plan({**good, "risk": "local_write"}, registry)
    with pytest.raises(PlanValidationError):
        validate_plan({**good, "needs_network": False}, registry)


def test_nested_tool_arguments_reject_extra_fields(registry):
    class Nested(BaseModel):
        text: str

    class Args(BaseModel):
        nested: Nested

    class NestedTool(FakeTool):
        name = "test.nested"
        input_model = Args

    registry.register(NestedTool())
    with pytest.raises(PlanValidationError):
        validate_plan(
            payload(
                steps=[
                    {
                        "tool": "test.nested",
                        "args": {"nested": {"text": "x", "hidden_action": "secret"}},
                    }
                ]
            ),
            registry,
        )


@pytest.mark.parametrize("threshold", [True, -0.1, 1.1, float("nan"), float("inf")])
def test_invalid_confidence_threshold_is_a_configuration_error(registry, threshold):
    with pytest.raises(ValueError, match="Confidence threshold"):
        validate_plan(payload(), registry, confidence_threshold=threshold)


def test_valid_custom_confidence_threshold_is_respected(registry):
    assert validate_plan(
        payload(confidence=0.7), registry, confidence_threshold=0.8
    ).requires_clarification
