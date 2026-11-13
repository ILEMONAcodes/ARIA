import pytest
from pydantic import TypeAdapter, ValidationError

from agent.contracts.events import AgentEvent, ConfirmRequest, UIEvent
from agent.contracts.plan import Plan


def test_valid_plan_parses():
    plan = Plan(
        intent="open_app",
        confidence=0.9,
        steps=[{"tool": "apps.launch", "args": {"name": "excel"}}],
    )
    assert plan.risk == "none"


def test_risk_above_none_requires_confirmation():
    with pytest.raises(ValidationError):
        Plan(intent="send", confidence=0.9, risk="external_send", needs_confirmation=False)


def test_confidence_out_of_range_is_rejected():
    with pytest.raises(ValidationError):
        Plan(intent="x", confidence=1.5)


def test_agent_event_union_picks_type_by_discriminator():
    ev = TypeAdapter(AgentEvent).validate_python(
        {"v": 1, "type": "reply.text", "task_id": "t1", "text": "hi", "spoken": True}
    )
    assert ev.type == "reply.text"


def test_unknown_event_type_is_rejected():
    with pytest.raises(ValidationError):
        TypeAdapter(AgentEvent).validate_python({"v": 1, "type": "nope"})


def test_confirm_request_defaults_to_needs_click():
    ev = ConfirmRequest(
        confirm_id="c", task_id="t", risk="external_send", dry_run_text="Send email"
    )
    assert ev.needs_click is True


def test_ui_confirm_response_requires_via():
    with pytest.raises(ValidationError):
        TypeAdapter(UIEvent).validate_python(
            {"v": 1, "type": "confirm.response", "confirm_id": "c", "decision": "yes"}
        )
