# Phase A contract and mock-agent handoff

Backend-owned handoff artifacts are ready for frontend F0. The desktop UI and
Tauri app are not scaffolded by this work. The API event schemas remain version
1 and are unchanged. No real tools, model calls, audio capture, mail or file
opening occur in the mock.

The Phase A foundation gate passed hosted backend/contract CI, including strict
type compilation, a live localhost policy replay, and Windows/macOS mock tests.
The implementation is merged into main; the actual app/voice loop and installer
are not complete.

## Set up the development tools

Use Python 3.11, uv 0.13.7, Node 24 and pnpm 9.15.9 (via Corepack). From the
repository root:

```sh
uv sync --locked --all-packages --all-extras
cd scripts/contract
corepack pnpm install --frozen-lockfile
cd ../..
uv run --locked --all-packages --all-extras pre-commit install
```

Node and the contract generator are build/development dependencies; they do
not add a Node requirement to the staff PC's Python agent at runtime.

## Generate and verify the types

The Pydantic models in `services/agent/src/agent/contracts` remain the source of
truth. The generation chain is Pydantic, then JSON Schema, then TypeScript:

```sh
uv run --locked --all-packages --all-extras python scripts/gen_contract.py
node scripts/contract/generate.mjs
uv run --locked --all-packages --all-extras python scripts/check_backend.py
node scripts/contract/check.mjs
```

The generated files are in `apps/desktop/src/contract/`:

| File | Exports |
| --- | --- |
| `schema.json` | Combined Pydantic JSON schemas and contract version |
| `agent-events.ts` | Agent event union and its model definitions |
| `ui-events.ts` | UI event union and its model definitions |
| `plan.ts` | Plan and step types |
| `index.ts` | Public named models, `CONTRACT_VERSION`, `WireAgentEvent`, `WireUIEvent` |

Import from the contract directory. Use `WireAgentEvent` and `WireUIEvent` for
transport: they require an explicit `v: CONTRACT_VERSION` and `type`.
The raw generated models reflect Pydantic constructor defaults, so those two
fields are optional in the raw types. Defaulted data fields may also be optional
(for example `citations`); use the documented defaults when consuming them.
These helpers do not change the wire schema.

```ts
import { CONTRACT_VERSION } from "./contract";
import type { WireUIEvent } from "./contract";

const approval: WireUIEvent = {
  v: CONTRACT_VERSION,
  type: "approval.response",
  approval_id: "a1", // Use the ID received from the pending request.
  decision: "yes",
};
```

`scripts/contract/examples.generated.ts` compiles every emitted fixture event
and every scenario response example against these types. `consumer.test.ts`
checks union narrowing and rejects missing input methods, voice-only approval,
missing discriminators and unsupported transport versions. Generator tests
verify read-only freshness checks and rejection of external schema references.
`--check` never rewrites stale generated files. CI checks Python schema
freshness, TypeScript freshness and strict compilation separately.

When the frontend package is created, its `gen:types` script can delegate to
`node ../../scripts/contract/generate.mjs`; install the contract tools first.
Do not hand-edit generated files or create a second set of event definitions.

## Connect to the mock agent

List available fixtures, then start one:

```sh
uv run --locked --all-packages --all-extras python -m agent.mock --list
uv run --locked --all-packages --all-extras python -m agent.mock --scenario policy_question
```

The mock binds only to `127.0.0.1:8765` and prints a WebSocket URL containing a
random session token. Connect using the entire printed URL:
`ws://127.0.0.1:8765/ws?token=<session-token>`.
Use the same token as `Authorization: Bearer <session-token>` for
`GET http://127.0.0.1:8765/api/health`.
Missing/wrong tokens are rejected. If a development harness needs a known token,
set `ARIA_MOCK_TOKEN` to a URL-safe value of at least 16 characters in its process
environment. This is a mock session token, never the gateway installation token.
Request logging is suppressed so URLs do not copy the token into access logs.
The mock exposes `/ws` and `/api/health` only; it does not implement the other
REST endpoints listed for the eventual real agent.

For browser REST fetches, pass `--allow-origin` with the exact origin printed
by your frontend development server. For example, if it is
`http://localhost:5173`, start the mock with
`--allow-origin http://localhost:5173`. Repeat the flag for additional known UI
origins. CORS is disabled by default; wildcards are rejected. Preflight checks
may succeed without a token, but the actual health request still needs Bearer
authentication. This option does not select the frontend's port or scaffold it.

`--port` selects another localhost port. `--no-delays` skips fixture pauses for
smoke checks; it does not measure real-agent latency. Normal replay preserves
the declared pauses, including the fallback fixture's eight-second delay.

## Scenario interactions

| Scenario | UI interaction needed to finish |
| --- | --- |
| `policy_question` | Approve cloud request `a1`, then send `source.open` using the returned citation's path and page |
| `email_reply_confirm_and_send` | Approve `a1`, then confirm `c1` via click or key |
| `offline_send_then_reconnect` | Confirm `c1` via click or key |
| `cloud_down_fallback` | None; replay ends after the fallback message |

Use the IDs and fields received during the connection; the table describes the
current fictional fixtures. Wait steps include a typed `match` example with
the complete expected UI response. See `tests/e2e/scenarios/README.md`.
The mock ignores unrelated response types and IDs. A matching decline or
`task.cancel` ends the replay without later success/outbox events. Both click
and key are accepted for confirmation; voice-only confirmation is invalid.
Malformed messages and unsupported/missing versions close the connection with
code 1008. Normal completion, decline and cancellation close with code 1000.
Each new connection starts a fresh replay; account for normal mock completion
when testing the frontend's eventual reconnect behavior.

Run the full mock tests without real network services:

```sh
uv run --locked --all-packages --all-extras python -m pytest -c services/agent/pyproject.toml services/agent/tests/unit/test_mock_agent.py
```

All four fixtures are replayed through the actual mock ASGI/WebSocket handler
using an in-process test client. These checks prove the handoff and event flow,
not the real policy, email, outbox or cloud implementations. The cited sample
file paths are fixture data; the mock does not create or open those files.
The real foundation CLI from A4 still does not serve the desktop API or voice
loop. Those runtime adapters follow in their planned phases.

For a separate live loopback integration check, run
`uv run --locked --all-packages --all-extras python scripts/smoke_mock.py`.
It starts its own temporary mock process on an ephemeral localhost port,
checks health authentication, completes the policy replay and stops the process.
This is intentionally separate from the network-blocked unit-test run and
uses only fictional credentials; no external proxy or service is involved.
