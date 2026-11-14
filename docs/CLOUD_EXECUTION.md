# Phase C6: approved gateway plans reach the executor

Implements Phase C's router/planner integration for DEP-3, DEP-4, SYS-1,
CAL-1 and SYSX-3 foundations. Provider accounts, API keys, speech assets,
new tools and real sends/deletes remain outside this change.

## Session flow

A trusted application assembly creates a `LocalSession` with a `CloudFlow` and
an `ExecutionEngine`. It starts/closes the injected adapter and network outside
the session, as before. Call `session.request_cloud(ModelRequest(...))` explicitly;
unknown `text.input` commands remain local and are never automatically uploaded.
The existing `agent.local` CLI/server still disables cloud use. This is the
internal integration boundary for the future hosted/voice application assembly,
not a new UI event accepting arbitrary plans, prompts or credentials.

1. Show C3's exact payload preview and wait for its correlated `approval.response`.
2. The gateway flow applies its shared timeout/retry budget and validates plan
   responses against its registry. It emits its existing response/clarification/
   fallback events; it still never runs tools.
3. The session waits in an owned background task. Only a completed outcome with
   a validated, complete plan can reach the executor. Ordinary answer, summary,
   draft and reply text is displayed without interpreting it as an action plan.
4. Recheck both the session executor's and cloud flow's Hosted/cloud-enabled
   settings. Submit the plan to the executor, which copies and validates it again
   against its own current registry, policy and confidence threshold.
5. Run through C4/C5's execution path. Each risky step has a separate click/key
   confirmation showing resolved values. A cloud payload approval authorizes
   only the upload, never any tool action. Tools are not retried on failure.

`cloud_plan_execution.json` documents the exact event sequence: initial status,
payload approval, thinking, the existing cloud plan preview/activity/status, then
the executor preview and two separately confirmed dependent fictional steps.
Planning and execution retain their own task IDs; `task.cancel` accepts the active
cloud or execution task ID. While the payload dialog has only an approval ID,
Stop or typed cancel revokes it. No public v1 event/schema fields change.

## Ownership and cancellation

A session permits one current request. New cloud requests or typed input replace
the previous request. Stop, matching task cancellation, close/disconnect or an
explicit session cancellation revoke outstanding payload approvals, cancel/join
submission and result-observer tasks, cancel the gateway request, then cancel the
executor. The result observer never holds the session transition lock. A slow
connectivity probe remains cancellable; it cannot block Stop behind the lock.

Joining the observer before cancelling the executor prevents it from starting
new work after cancellation completes, including when cancellation arrives during
executor submission. Epoch checks reject stale outcomes. Even an adapter returning
late after cancellation cannot release tools. Old approval and confirmation IDs
remain single use. A closed session cannot start another request.

Existing execution limits still apply: completed actions are not rolled back,
and an interrupted action may already have taken effect. Activity records those
facts. Cloud failure/clarification/decline never dispatches an execution plan;
invalid handoff or executor policy changes stop safely with sanitized diagnostics.
Session activity is not yet durable profile history.

## Verification and remaining gates

`test_cloud_execution.py` uses sockets-blocked fake adapters/networks, the actual
in-memory gateway API with a fictional provider and the real plan validator and
executor with an in-memory tool runner. It checks the full scenario, payload/action
approval separation, bindings, replay/decline, invalid/incomplete plans, retries,
fallback, changed policy/registry and cancellation/replacement across phases.
It launches no apps and performs no real sends, writes or deletes.

The separate `scripts/smoke_execution.py` additionally verifies fake-provider
handoff into actual isolated dependent workers on Linux, Windows and macOS.
Provider setup, real Windows/frontend acceptance, latency, voice integration and
profile-bound persistence remain open; this does not pass the full Phase C gate.
