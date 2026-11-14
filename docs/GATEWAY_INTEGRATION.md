# Phase C3: gateway client, approval and retry/fallback

Implements the agent-to-gateway integration and bounded cloud-request handling
for DEP-3/DEP-4 and the Phase C plan/router rules. Live provider selection and
setup are deferred at the user's request (decision 30). This component is tested
against the real gateway ASGI application with a fake provider, never a paid
model or real staff data.

## Components

- `agent.llm.gateway.GatewayClient` implements `LLMAdapter` and `Network`. Startup
  prepares an HTTP client without contacting a service; `is_online()` probes
  the actual `/health` endpoint without task data or an installation token.
- `agent.llm.wire` validates and serializes only the documented gateway fields.
  Source text stays in `data_blocks`, and the packaged data-block instruction
  rule is added to system messages before approval. Request previews are bounded
  to 64 KiB, responses to 1 MiB, and health bodies to 1 KiB.
- `agent.llm.flow.CloudFlow` owns one pending/active request per authenticated
  desktop session. It exposes `submit`, `approve`, `wait`, `cancel` and `close`.
  Adapters are started/closed by the caller, not implicitly by the flow.

The HTTP client uses the configured HTTPS gateway URL and environment-only
installation token. The token is sent in the Authorization header, never in
the JSON/approval preview. TLS verification stays enabled; redirects and
environment proxies are disabled. The agent does not have a model provider key.

## Approval and policy

`submit(ModelRequest(...))` first checks Hosted/cloud-enabled policy and actual
gateway connectivity. It copies and validates the request and emits a v1
`cloud.approval_request` whose `payload_preview` is the exact JSON body that
will be posted. No task data is sent before approval; only data-free health
probes may run. Changes to the caller's schema dictionary cannot change the
pending request. Starting a new request clears/cancels the old one.

Call `approve(ApprovalResponse(...))` with the matching approval ID. Wrong IDs,
unsupported versions and replayed responses cannot send a request. Decline
sends nothing. Approval consumes the pending request before scheduling it;
`wait()` returns its result. The flow rechecks policy/connectivity after approval
and before each attempt. Local profile and admin-disabled cloud never call the
model; no local language model is claimed to be implemented.

`GatewayClient.complete` is the lower-level single-attempt adapter, for trusted
assembly code. Route application cloud requests through `CloudFlow` so approval
is enforced. There is no session-wide implicit approval in C3. Future settings
or endpoint changes must cancel the flow and reassemble its adapter.

## Retry, deadline and fallback

After approval, one wall-clock budget (`cloud_timeout_s`, default/max 8 seconds)
covers connectivity rechecks, up to two model attempts and the short backoff.
An individual attempt gets at most half the total budget so a stalled first
call leaves time for a retry; the outer deadline limits the remaining work.
UI status and a retry caption give progress. Final UI delivery happens outside
the network deadline so a slow UI cannot turn a received response into an error.

Connection/transport failures, HTTP 408/5xx and attempt timeouts can retry once.
HTTP 401/403/422/429, redirects, malformed/mismatched/oversized responses and
other permanent rejections fall back without retrying. The HTTP adapter has no
nested retry mechanism. A request UUID is stable across attempts for correlation;
the development gateway does not deduplicate model calls, so two attempts may
consume two provider calls. No irreversible actions run in either attempt.

For `task="plan"`, C1 validation checks the returned JSON and registered tools.
Invalid output gets at most one retry within the same two-attempt budget, then
one rephrase question. Low-confidence/missing information also returns
clarification. A valid plan emits `plan.preview`; it never executes a tool or
bypasses action confirmation. Grounding names/dates/amounts remains planner work.

On failure, emit one error, a caption offering local commands/retry, a plain
session activity entry and idle status. The result is `fallback`; the later
dispatcher can continue with configured local tools/retrieval. C3 does not fake
local results or queue/send mail. `online:false` here indicates unavailable cloud
service, not an OS-level internet measurement. Captions use `spoken:false` until
speech-output integration exists.

`cancel()` clears pending approval, cancels the current async request and stops
retry/final-result emission. It cannot retract a request already accepted by the
gateway/provider, which may still finish or bill it. Session teardown must await
`close()` before releasing its adapters. `wait()` alone is not a cancellation API.

## Assembly example

After loading settings with `ARIA_GATEWAY_URL` and `ARIA_INSTALL_TOKEN`:

```python
from agent.llm.gateway import GatewayClient
from agent.llm.flow import CloudFlow

client = GatewayClient(settings)
await client.start()
flow = CloudFlow(settings, client, client, emit_event, registry=registered_tools)
try:
    approval_id = await flow.submit(model_request)
    # Pass the matching validated UI approval.response to flow.approve().
    # It schedules the request, allowing the receiver to keep handling cancel.
finally:
    await flow.close()
    await client.close()
```

The per-session owner must authenticate UI events, route cancellation, deliver
the emitted events, and render the preview without truncating it. The existing
voice echo server is unchanged. C4's local text dispatcher (LOCAL_EXECUTION.md)
offers an explicit cloud-request boundary; automatic AI planning and voice/desktop
integration remain pending. No public desktop event fields or versions changed.

## Gateway rendering and errors

The gateway keeps document/email source in escaped `<data>` blocks: metadata
quotes and source closing tags cannot break the wrapper. It also adds the data
instruction rule if an authenticated client omitted it. This is a prompt
boundary, not proof that a real model resists prompt injection; adversarial
model evaluations and action approval remain required.

Provider exceptions map to sanitized 502 responses and timeouts to 504. Bodies
contain no provider exception text, source text or keys. Existing development
rate/spend counters remain in memory and are not production billing controls.
The real `ProviderLLM` implementation is still unconfigured; calling it returns
the safe provider-error path. C3 does not deploy a gateway or contact Gemma.

## Verification and deferred setup

The new `gateway_retry_fallback` mock scenario was added before implementation;
the real controller test compares its event flow and byte-exact approval preview
against that fixture. No contract schema change is needed.

`test_gateway_client.py` tests request/response limits, token separation,
status classification, correlation, health probes and lifecycle guards.
`test_cloud_flow.py` tests approval/decline/replay, immutable previews, policy and
network changes, timeout/retry limits, invalid plans, cancellation and real
client-to-gateway ASGI integration with fake success/failure providers. Network
sockets stay blocked. Gateway tests verify escaped data wrappers and safe errors.

The user's remaining tasks are listed in ROADMAP.md: choose a provider, create
the account/key, set the budget/terms, implement/configure the chosen adapter,
then run approved live tests. Voice-model setup and evaluation remain deferred.
