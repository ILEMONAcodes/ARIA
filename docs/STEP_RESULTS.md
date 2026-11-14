# Phase C5: safe step-result bindings

Implements TECH_SPEC section 4's `$stepN.field` rule for the Phase C execution
path (SYS-1, CAL-1, SYSX-3 foundations). No model/provider setup or real send,
delete, document write or new tool capability is added.

## Syntax and data flow

Step numbers start at one. A later argument may use an entire declared field
from a completed earlier step:

```json
{
  "intent": "dependent_example",
  "confidence": 1,
  "steps": [
    {"tool": "test.produce", "args": {}},
    {"tool": "test.consume", "args": {"name": "$step1.name"}}
  ]
}
```

These example tools are fictional test fixtures, not production file-writing
tools. Bindings may appear inside nested dictionaries/lists, or replace a whole
object/list argument. Numbers, booleans, nulls and containers retain their types;
there is no string conversion, list splicing or expression evaluation.

Only the exact, case-sensitive, whole-string form `$stepN.field` is accepted.
`N` is a positive one-based number with at most six digits; `field` is a public
identifier up to 128 characters. The source must be an earlier step with a
registered output model declaring that non-excluded field. Forward/self/cyclic
bindings, missing/private fields, nested attribute/index traversal, function
calls and string interpolation are rejected. `$step` is reserved in template
argument values and cannot appear in dynamic keys, slots, intent or missing-slot
metadata. This syntax is intentionally narrower than a scripting language.

The resolver reads only the executor's already validated outputs. It copies the
selected JSON value and stops there: returned text such as `$step99.example`
remains ordinary source data, never a second instruction/binding. Every argument
gets its own copy; a consumer cannot mutate an earlier result through that copy.

## Two validation stages

`validate_plan` checks every binding's syntax, order and declared source field
before any execution. Pure-literal steps retain full strict Pydantic preflight.
Dependent argument templates receive an additional closed JSON Schema check for
known structure, required/extra fields and available literal constraints.
Unresolved values and constraints depending on them defer until resolution.
No remote/file schema retrieval is enabled; explicit schema references must be
local, and the validator receives a no-retrieval registry.

Template checking is not proof that all future inputs will be valid. Pydantic
custom validators, constraints involving unknown values, and some union or
conditional constraints require actual results. Immediately before a dependent
step's dry run, the executor resolves the arguments and runs the complete strict
Pydantic input validation, including custom validators. Wrong types, null where
disallowed, missing serialized output fields or invalid resolved values stop the
workflow before that consumer's preview/action. It rechecks arguments and tool
policy again before the action.

## Confirmation and cancellation

Risk rules are unchanged. Any required confirmation is generated from fully
resolved and normalized arguments, never a placeholder. It uses a fresh
single-use ID and click/key approval; voice alone, stale IDs, decline or cancel
cannot release the step. Dry runs receive separate copies. Their argument
mutation is rejected by the executor and the real worker. The executor also
requires normalized arguments to remain identical after confirmation, and the
worker rejects validation that changes those normalized values before running.

Registered tools/validators remain trusted, pure/deterministic application code.
Dry-run implementations must describe all recipients/destinations/side effects;
the framework cannot prove that arbitrary tool prose describes its code.
No new general execution authority comes from a binding or a confirmation.

Failed/invalid/timed-out/cancelled producers do not publish results for later
steps. Declining a dependent step leaves completed earlier steps intact and runs
no later action. This is serial execution, not a transaction or rollback:
earlier steps may already have completed before a later resolved input fails.
Activity retains those counts and reports uncertainty for interrupted effects.

## Tests and handoff

`test_step_results.py` uses fictional in-memory tools with sockets blocked. It
covers the graph/grammar, nested typed values, one-pass copy semantics, literal
schema checks, custom validation, absent/wrong/null fields, resolved confirmations,
replay/decline, caller/preview mutation and producer failure/cancellation.
Its confirmation/event sequence matches `dependent_steps.json`, which the mock
also replays. The public v1 Plan and event schemas remain unchanged; only new
scenario examples are generated for the frontend handoff.

`scripts/smoke_execution.py` additionally executes a three-step dependency chain
through actual workers and verifies that a mutating dry run is rejected. It still
uses no real app, provider, network or confidential file. The platform matrix
runs the new tests and this smoke check on Windows/macOS, alongside Linux CI.

Bindings are a backend plan/executor capability; the local keyword matcher and
text API do not accept arbitrary plans directly from the UI. Frontend acceptance,
durable profile-bound history, deployment and the deferred voice/provider tasks
remain separate gates.
