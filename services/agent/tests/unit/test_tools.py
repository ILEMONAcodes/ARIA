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
