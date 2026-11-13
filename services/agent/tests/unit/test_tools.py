import pytest
from pydantic import BaseModel

from agent.tools import Tool, ToolRegistry


class In(BaseModel):
    name: str


class Out(BaseModel):
    ok: bool


class FakeOpen(Tool[In, Out]):
    name = "apps.launch"
    risk = "none"
    needs_network = False
    timeout_s = 5.0
    input_model = In
    output_model = Out
    ran = False

    def dry_run(self, args: In) -> str:
        return f"Open {args.name}"

    def run(self, args: In) -> Out:
        type(self).ran = True
        return Out(ok=True)


def test_registered_tool_can_be_fetched():
    reg = ToolRegistry()
    reg.register(FakeOpen())
    assert reg.get("apps.launch").name == "apps.launch"


def test_unknown_tool_is_rejected():
    with pytest.raises(KeyError):
        ToolRegistry().get("shell.exec")


def test_tool_without_declarations_cannot_register():
    class Bad(Tool[In, Out]):  # type: ignore[type-arg]
        name = "bad.tool"

        def dry_run(self, args: In) -> str:
            return ""

        def run(self, args: In) -> Out:
            return Out(ok=True)

    with pytest.raises(ValueError):
        ToolRegistry().register(Bad())


def test_dry_run_has_no_side_effects():
    FakeOpen.ran = False
    text = FakeOpen().dry_run(In(name="excel"))
    assert text == "Open excel"
    assert FakeOpen.ran is False


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("name", "shell command"),
        ("name", "Apps.Open"),
        ("risk", "unknown"),
        ("needs_network", "false"),
        ("timeout_s", True),
        ("timeout_s", 0),
        ("timeout_s", -1),
        ("timeout_s", float("inf")),
        ("timeout_s", float("nan")),
        ("input_model", In(name="x")),
        ("output_model", str),
    ],
)
def test_invalid_tool_declarations_fail_before_registration(attribute, value):
    class Invalid(FakeOpen):
        pass

    setattr(Invalid, attribute, value)
    registry = ToolRegistry()
    with pytest.raises((TypeError, ValueError)):
        registry.register(Invalid())
    assert registry.names() == []


def test_duplicate_tool_registration_cannot_replace_an_implementation():
    registry = ToolRegistry()
    first = FakeOpen()
    registry.register(first)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeOpen())
    assert registry.get(first.name) is first


def test_every_tool_has_schema_risk_network_need_timeout():
    registry = ToolRegistry()
    registry.register(FakeOpen())
    definition = registry.describe()[0]
    assert definition["name"] == "apps.launch"
    assert definition["risk"] == "none"
    assert definition["needs_network"] is False
    assert definition["timeout_s"] == 5.0
    assert definition["input_schema"]["properties"]["name"]["type"] == "string"
    assert definition["output_schema"]["properties"]["ok"]["type"] == "boolean"
    definition["input_schema"]["properties"].clear()
    assert "name" in registry.describe()[0]["input_schema"]["properties"]


def test_registry_captures_policy_at_registration():
    class Mutable(FakeOpen):
        pass

    registry = ToolRegistry()
    registry.register(Mutable())
    Mutable.risk = "external_send"
    Mutable.needs_network = True
    assert registry.spec("apps.launch").risk == "none"
    assert registry.spec("apps.launch").needs_network is False
