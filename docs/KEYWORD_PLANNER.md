# Phase C2: local keyword planner

Supports SYS-1, CAL-1 and SYSX-3. `agent.planner.KeywordPlanner` implements the
stateless `KeywordMatcher` interface, separate from the later async model
`Planner`. It reads user command text and produces internal match results;
it does not open apps, read a calendar, cancel a running job or call the cloud.

## Matching rules

| Command | Result |
|---|---|
| `Open Excel` | Validated `apps.launch` plan, `{"name":"excel"}`, if configured/registered |
| `opn Excel` | Same plan with lower confidence; RapidFuzz permits one edit in `open` |
| `What's on my calendar today?` | Validated `cal.list` plan with the current local ISO date |
| `Cancel` or `stop` | Cancellation control outcome for the later dispatcher |
| `Open` / unknown or ambiguous app name | One clarification question |
| `Show my calendar` | Ask which day; do not invent a date |
| `Write a memo` | `no_match`, reserved for the future AI-planner handoff |

Normalization handles case, whitespace, curly apostrophes, terminal sentence
punctuation and a single polite prefix (`please`, `can you`, `could you`) plus
a trailing `please`. Matching uses the entire command, never a keyword search
inside a document or paragraph. Negated/quoted/compound inputs do not produce
local action plans in the covered tests. This is bounded grammar, not a general
English parser; unsupported phrasing needs the later planner/clarification path.

Only the opening verb is fuzzy-matched. App IDs/names/aliases must match the
injected catalog exactly after normalization. For `opn exel`, `exel` must be
explicitly configured as an alias; otherwise ARIA asks instead of guessing.
Shared aliases are ambiguous. No installed app names or executable paths are
assumed. The future launcher must independently enforce its executable allow-list.

`today` is resolved from an injected timezone-aware `Clock` and explicit local
timezone on every request. No host timezone, frozen startup date or model guess
is used. Calendar phrases with other dates and file-finding commands are not
implemented here; their matching/tool support remains future work.

## Assembly and outcomes

Construct `KeywordPlanner(registry, apps=..., clock=..., time_zone=...)` with
trusted installation configuration. For example, `apps` may be
`{"excel": ("microsoft excel", "exel"), "word": ("microsoft word",)}` on an
installation where those IDs have been configured. The constructor copies the
catalog; limits are 256 apps, 32 aliases per app, and 80 characters per alias.
Commands are limited to 512 characters.

Register the actual tools before matching; C2 unit tests use stubs whose `run`
and `dry_run` methods raise if invoked. `apps.launch` takes a `name` app ID and
`cal.list` takes a `date` ISO string. These are internal tool arguments; no v1
contract fields changed. Missing tools, incompatible schemas or a tool needing
network return `unavailable`. Generated plans copy registered risk/confirmation
policy and pass C1's `validate_plan` before being returned.

`KeywordResult.kind` is one of:

- `plan`: carries the validated plan. This is not approval or execution authority.
- `clarify`: carries one question and no plan; wait for the user's answer.
- `cancel`: no plan or fabricated task ID; dispatcher cancels its current task.
- `no_match`: no local interpretation. It does not automatically authorize cloud
  use; the future model/router path still needs payload approval.
- `unavailable`: a known command cannot be planned with the available local tools.

Feed only direct user commands/transcripts to this interface. Documents, emails
and other source content remain data blocks, never local commands.

## Tests and remaining integration

`test_keywords.py` verifies exact/alias/verb-typo matching, ambiguity,
clarification, local-date rollover, cancellation, unknown/negated/compound text,
unavailable tools and preserved risk. Tests run with sockets blocked and never
invoke tool code or write files. A generous one-second per-command CPU
regression check is not an end-to-end Windows performance measurement.

This internal component does not change UI behavior, so no scenario or event
schema is added here. Real app/calendar adapters, dispatcher/runtime wiring,
AI fallback, approvals and end-to-end activity events remain later Phase C work.
The voice assets and real speech evaluation stay on the deferred-work list.
