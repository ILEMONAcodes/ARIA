"""Fictional dependent tools: no files, models, network, sends or deletes."""

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from typing import Any, Literal

import pytest
from pydantic import BaseModel, Field, model_validator

from agent.config import Settings
from agent.contracts.events import ConfirmResponse
from agent.contracts.plan import Plan
from agent.fakes import FakeNetwork, FakeTool
from agent.mock.scenarios import load_scenario
from agent.planner.references import ReferenceError, resolve_args
from agent.planner.validation import PlanValidationError, validate_plan
from agent.router.executor import PlanExecutor
from agent.tools import ToolRegistry


class Empty(BaseModel):
    pass


class Produced(BaseModel):
    name: str
    count: int = 3
    payload: dict[str, Any] = {"items": ["fictional"], "label": "$step99.never_interpret"}
    optional: str | None = None


class ConsumerInput(BaseModel):
    name: str


class Message(BaseModel):
    message: str


class Producer(FakeTool):
    name = "test.produce"
    input_model = Empty
    output_model = Produced

    def dry_run(self, args):
        return "Produce the fictional document name."

    def run(self, args):
        return Produced(name="fictional-report.docx")


class Consumer(FakeTool):
    name = "test.consume"
    input_model = ConsumerInput
    output_model = Message

    def dry_run(self, args):
        return f"Use {args.name}."

    def run(self, args):
        return Message(message=f"Used {args.name}.")


def make_registry(consumer=Consumer, producer=Producer):
    registry = ToolRegistry()
    registry.register(producer())
    registry.register(consumer())
    return registry


def dependent(args=None, *, risk="none"):
    return Plan(
        intent="dependent",
        confidence=1,
        risk=risk,
        needs_confirmation=risk != "none",
        steps=[
            {"tool": "test.produce", "args": {}},
            {"tool": "test.consume", "args": args if args is not None else {"name": "$step1.name"}},
        ],
    )


class Runner:
    def __init__(self):
        self.calls = []
        self.hold_producer = False
        self.started = asyncio.Event()
        self.fail_producer = False
        self.bad_producer_output = False
        self.mutate_preview = False

    async def invoke(self, tool, args, *, mode, timeout_s):
        self.calls.append((tool.name, mode, deepcopy(args)))
        if mode == "dry_run":
            if self.mutate_preview and tool.name == "test.consume":
                args["name"] = "changed.docx"
            return tool.dry_run(tool.input_model.model_validate(args))
        if tool.name == "test.produce":
            self.started.set()
            if self.hold_producer:
                await asyncio.Event().wait()
            if self.fail_producer:
                raise RuntimeError("private source must not leak")
            if self.bad_producer_output:
                return {"name": 123}
        return tool.run(tool.input_model.model_validate(args)).model_dump(mode="json")


@asynccontextmanager
async def running(registry=None):
    registry = registry or make_registry()
    events = []

    async def emit(event):
        events.append(event.model_dump(mode="json", exclude_none=True))

    network = FakeNetwork()
    await network.start()
    runner = Runner()
    executor = PlanExecutor(registry, Settings(), network, emit, runner=runner)
    try:
        yield executor, runner, events
    finally:
        await executor.close()
        await network.close()


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0)


def test_valid_dependent_plan_resolves_from_validated_output():
    async def scenario():
        async with running() as (executor, runner, events):
            await executor.submit(dependent())
            result = await executor.wait()
            assert result.kind == "completed" and result.completed_steps == 2
            assert runner.calls == [
                ("test.produce", "run", {}),
                ("test.consume", "run", {"name": "fictional-report.docx"}),
            ]
            assert any(e.get("text") == "Used fictional-report.docx." for e in events)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "reference",
    [
        "$step0.name",
        "$step01.name",
        "$step2.name",
        "$step3.name",
        "$step-1.name",
        "$step1.missing",
        "$step1.__class__",
        "$step1.payload.items",
        "$step1.payload[0]",
        "$step1.name()",
        "prefix $step1.name",
        "$step1.name/suffix",
        "$step",
        "$step1.",
    ],
)
def test_invalid_references_are_rejected_before_any_tool_runs(reference):
    async def scenario():
        async with running() as (executor, runner, events):
            await executor.submit(dependent({"name": reference}))
            assert runner.calls == []
            assert any(e.get("code") == "invalid_plan" for e in events)

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "args",
    [
        {"name": "$step1.name", "hidden": "unexpected"},
        {"$step1.name": "not a dynamic key"},
        {"wrong": "$step1.name"},
    ],
)
def test_template_unknown_and_missing_fields_fail_preflight(args):
    with pytest.raises(PlanValidationError):
        validate_plan(dependent(args), make_registry())


def test_nested_lists_and_dict_bindings_preserve_types_and_copy_values_once():
    template = {"payload": "$step1.payload", "values": ["constant", "$step1.count"]}
    output = Produced(name="fictional").model_dump(mode="json")
    resolved = resolve_args(template, [output])
    assert resolved["values"] == ["constant", 3]
    assert resolved["payload"]["label"] == "$step99.never_interpret"
    resolved["payload"]["items"].append("changed")
    assert output["payload"]["items"] == ["fictional"]
    assert template["payload"] == "$step1.payload"


def test_typed_nested_argument_templates_validate_literals_before_resolution():
    class Nested(BaseModel):
        count: int
        label: Literal["allowed"]

    class Args(BaseModel):
        nested: Nested
        values: list[int] = Field(min_length=1)

    class TypedConsumer(Consumer):
        input_model = Args

    registry = make_registry(TypedConsumer)
    assert validate_plan(
        dependent(
            {"nested": {"count": "$step1.count", "label": "allowed"}, "values": ["$step1.count", 4]}
        ),
        registry,
    )
    for args in [
        {"nested": {"count": "$step1.count", "label": "wrong"}, "values": [4]},
        {"nested": {"count": "$step1.count", "label": "allowed", "extra": True}, "values": [4]},
        {"nested": {"count": "$step1.count", "label": "allowed"}, "values": []},
    ]:
        with pytest.raises(PlanValidationError):
            validate_plan(dependent(args), registry)


def test_executor_passes_nested_typed_values_without_mutating_producer_results():
    class Args(BaseModel):
        payload: dict[str, Any]
        counts: list[int]
        absent: str | None

    class NestedConsumer(Consumer):
        input_model = Args

        def run(self, args):
            assert args.counts == [3, 4]
            assert args.absent is None
            assert args.payload["label"] == "$step99.never_interpret"
            args.payload["items"].append("consumer changed its own copy")
            return Message(message="Nested values preserved.")

    async def scenario():
        async with running(make_registry(NestedConsumer)) as (executor, runner, _events):
            await executor.submit(
                dependent(
                    {
                        "payload": "$step1.payload",
                        "counts": ["$step1.count", 4],
                        "absent": "$step1.optional",
                    }
                )
            )
            result = await executor.wait()
            assert result.kind == "completed" and result.completed_steps == 2
            assert result.outputs[0]["payload"]["items"] == ["fictional"]
            assert runner.calls[-1][2]["counts"] == [3, 4]

    asyncio.run(scenario())


@pytest.mark.parametrize("field", ["count", "optional"])
def test_resolved_wrong_type_or_none_stops_before_consumer_preview_or_run(field):
    async def scenario():
        async with running() as (executor, runner, events):
            await executor.submit(dependent({"name": f"$step1.{field}"}))
            result = await executor.wait()
            assert result.kind == "failed" and result.completed_steps == 1
            assert runner.calls == [("test.produce", "run", {})]
            assert not any(e["type"] == "confirm.request" for e in events)

    asyncio.run(scenario())


def test_missing_serialized_field_and_excluded_field_fail_closed():
    with pytest.raises(ReferenceError):
        resolve_args({"name": "$step1.name"}, [{}])

    class Hidden(Produced):
        name: str = Field(exclude=True)

    class HiddenProducer(Producer):
        output_model = Hidden

    with pytest.raises(PlanValidationError):
        validate_plan(dependent(), make_registry(producer=HiddenProducer))


def test_declared_remote_schema_is_never_retrieved():
    class Remote(BaseModel):
        name: str = Field(json_schema_extra={"$ref": "https://not-contacted.invalid/schema"})

    class RemoteConsumer(Consumer):
        input_model = Remote

    with pytest.raises(PlanValidationError):
        validate_plan(dependent(), make_registry(RemoteConsumer))


def test_custom_cross_field_validation_runs_after_resolution():
    class Args(BaseModel):
        name: str

        @model_validator(mode="after")
        def rejects_name(self):
            raise ValueError("private custom validation detail")

    class Rejecting(Consumer):
        input_model = Args

    async def scenario():
        async with running(make_registry(Rejecting)) as (executor, runner, events):
            await executor.submit(dependent())
            outcome = await executor.wait()
            assert outcome.kind == "failed" and outcome.completed_steps == 1
            assert len(runner.calls) == 1
            assert "private custom validation detail" not in str(events)

    asyncio.run(scenario())


def test_resolved_confirmation_matches_scenario_and_decline_replay_are_safe():
    async def scenario():
        expected = [s for s in load_scenario("dependent_steps")["steps"]]
        async with running() as (executor, runner, events):
            original = dependent(risk="local_write")
            await executor.submit(original)
            original.steps[1].args["name"] = "changed by caller"
            received = 0
            for step in expected:
                if "send" in step:
                    await until(lambda received=received: len(events) > received)
                    actual = events[received]
                    received += 1
                    dynamic = {"id", "ts", "task_id", "confirm_id"}
                    assert {k: v for k, v in actual.items() if k not in dynamic} == {
                        k: v for k, v in step["send"].items() if k not in dynamic
                    }
                else:
                    confirmation = events[-1]
                    assert not await executor.confirm(
                        ConfirmResponse(confirm_id="wrong", decision="yes", via="click")
                    )
                    answer = ConfirmResponse(
                        confirm_id=confirmation["confirm_id"], decision="yes", via="click"
                    )
                    assert await executor.confirm(answer)
                    assert not await executor.confirm(answer)
            assert (await executor.wait()).kind == "completed"
            assert runner.calls[-1][2] == {"name": "fictional-report.docx"}

    asyncio.run(scenario())


def test_declining_resolved_consumer_preserves_completed_producer_and_never_consumes():
    class RiskyConsumer(Consumer):
        risk = "local_write"

    async def scenario():
        async with running(make_registry(RiskyConsumer)) as (executor, runner, events):
            await executor.submit(dependent(risk="local_write"))
            confirmations = 0
            while confirmations < 2:
                await until(
                    lambda confirmations=confirmations: (
                        sum(e["type"] == "confirm.request" for e in events) > confirmations
                    )
                )
                confirmation = events[-1]
                confirmations += 1
                await executor.confirm(
                    ConfirmResponse(
                        confirm_id=confirmation["confirm_id"],
                        decision="yes" if confirmations == 1 else "no",
                        via="key",
                    )
                )
            result = await executor.wait()
            assert result.kind == "declined" and result.completed_steps == 1
            assert not any(
                name == "test.consume" and mode == "run" for name, mode, _ in runner.calls
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("failure", ["fail_producer", "bad_producer_output", "hold_producer"])
def test_failed_invalid_or_cancelled_producer_never_releases_dependent_steps(failure):
    async def scenario():
        async with running() as (executor, runner, events):
            setattr(runner, failure, True)
            await executor.submit(dependent())
            if failure == "hold_producer":
                await runner.started.wait()
                await executor.cancel()
            else:
                assert (await executor.wait()).kind == "failed"
            assert not any(name == "test.consume" for name, _, _ in runner.calls)
            assert "private source must not leak" not in str(events)

    asyncio.run(scenario())


def test_mutating_preview_arguments_fails_without_running_consumer():
    async def scenario():
        async with running() as (executor, runner, events):
            runner.mutate_preview = True
            await executor.submit(dependent(risk="local_write"))
            await until(lambda: any(e["type"] == "confirm.request" for e in events))
            await executor.confirm(
                ConfirmResponse(confirm_id=events[-1]["confirm_id"], decision="yes", via="click")
            )
            outcome = await executor.wait()
            assert outcome.kind == "failed" and outcome.completed_steps == 1
            assert not any(
                name == "test.consume" and mode == "run" for name, mode, _ in runner.calls
            )

    asyncio.run(scenario())
