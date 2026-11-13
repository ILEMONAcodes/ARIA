# Phase C1: plan validation and tool registry

Supports the Phase C SYS-1, CAL-1 and SYSX-3 work and the plan/tool safety rules
in PRD section 4. This component validates data only. It does not implement
app launching, calendar access, cloud requests, approval or execution.

## Boundaries

`agent.tools.ToolRegistry` registers only concrete `Tool` implementations with
a dotted lowercase name, one of the four supported risks, a boolean network
declaration, a finite positive timeout, and Pydantic input/output model classes.
Duplicate names are rejected. Registration captures policy metadata in a frozen
`ToolSpec`; subsequent class-attribute changes do not change that policy.
Tool implementations and schema classes are trusted application code.

`describe()` returns fresh schema dictionaries for the future planner.
`validate_args()` validates strictly and forbids extra fields, including inside
nested models. It calls neither `dry_run()` nor `run()`. Pydantic schema/field
validators are trusted application code and must also have no side effects.

`agent.planner.validate_plan(payload, registry)` accepts JSON text, a dictionary,
or an existing `Plan` value. It:

- Rejects malformed JSON, duplicate JSON keys, non-finite values, unknown fields,
  invalid argument types and unregistered tools.
- Rejects a plan whose risk is lower than any registered step's risk, or whose
  `needs_network` is false when any step requires the network. Higher declared
  risk/network requirements are retained as conservative restrictions.
- Applies the existing rule that any risk above `none` needs confirmation.
- Returns a copied `PlanReview`, requiring clarification below confidence 0.6,
  for missing slots, or for an empty step list. `first_missing` exposes one slot
  at a time. The threshold can use the existing settings value.
- Raises a content-free `PlanValidationError("Invalid plan")` on invalid plans.
  It does not include supplied arguments, names or recipients in diagnostics.

The public v1 Plan/event schema and generated artifacts are unchanged. Stricter
checks happen at the internal ingestion boundary. Validating an existing Plan
cannot recover values discarded/coerced before it was constructed; untrusted
model responses must enter as raw JSON. The agent's minimum Pydantic version is
2.12 for per-call extra-field enforcement; the workspace lock still pins the
installed version.

## Example with a fake tool

```python
from agent.fakes.tools import FakeTool
from agent.planner import validate_plan
from agent.tools import ToolRegistry

registry = ToolRegistry()
registry.register(FakeTool())
review = validate_plan({
    "intent": "echo",
    "confidence": 0.9,
    "steps": [{"tool": "test.echo", "args": {"text": "fictional request"}}],
}, registry)
assert not review.requires_clarification
```

This performs no action. A review is not approval or execution authority. The
future executor must revalidate arguments and current policy, honor cancellation,
resolve references, enforce timeouts and require the applicable user approvals.
`$stepN.field` bindings currently fail closed until resolution and per-step
validation exist. No input provenance/grounding check is claimed here: matching
names, dates and amounts to transcript/contacts/calendar remains planner work.

## Verification and next work

`test_plan_validation.py` covers valid offline input, malformed/strict/nested
validation, unknown tools, risk/network understatement, clarification, caller
mutation isolation and safe errors. Tools used there raise if any `run` or
`dry_run` is invoked. `test_tools.py` covers declarations, duplicate registration,
policy capture and schema export. All run with network sockets blocked.

There is no UI-visible behavior change or transport wiring in C1, so no new
scenario or contract fields are needed. C2 adds the local keyword planner
(KEYWORD_PLANNER.md), followed by model/gateway integration, retry-once/rephrase handling, approval
and execution. The voice-model and real speech tasks remain deferred as recorded
in ROADMAP.md and decision 26.
