# Phase C4: local routing, execution and tools

Implements the non-model local path for SYS-1, CAL-1 and SYSX-3, confirmation
and activity reporting. No speech model, provider account or cloud connection
is required. This is Python development-mode execution; signed sidecar packaging
and real staff-PC/UI acceptance remain later checks.

## Try the local calendar now

From the repository root:

```sh
uv sync --locked --all-packages --all-extras
uv run --locked --all-packages --all-extras python -m agent.local --tools config/local-tools.example.toml --command "calendar today"
```

This reads `library/sample_calendar.ics`, a clearly fictional calendar, through
the actual executor/worker. It prints the calendar reply and activity entry.
The sample has a daily fictional event during 2026; an empty date is reported as
empty, never replaced by a guessed event. No app is launched by this example.

Copy `config/local-tools.example.toml` to the git-ignored `config/local-tools.toml`
to configure your own installation. Specify the timezone and local ICS path;
relative paths are relative to that TOML file. Add installed applications with
explicit IDs, aliases and absolute `.exe` paths. There are no default app paths,
command-line arguments, app discovery or shell commands.

```toml
timezone = "Africa/Lagos"
calendar = "../library/sample_calendar.ics"
# [apps.excel]
# executable = "C:/replace-with-your-installed-path/EXCEL.EXE"
# aliases = ["microsoft excel"]
```

On Windows, after configuring the actual path, use the same `--command` option
with `open excel`. The launcher starts only that configured executable with
`shell=False`, fixed working directory, no user arguments and a restricted
environment. It rechecks that the executable exists and still resolves to the
configured path. Application launching is Windows-only; no real app is launched
by unit tests or CI. A successful launch reports that the process was started,
not that the app's UI has finished loading.

The terminal command exits nonzero if it cannot complete. It never automatically
approves a risky tool: if confirmation is needed, that step is declined and the
user must use the connected UI controls instead.

## Desktop text transport

Omit `--command` to start the authenticated localhost service:

```sh
uv run --locked --all-packages --all-extras python -m agent.local --tools config/local-tools.example.toml
```

It prints a local session URL. A launcher may instead supply `ARIA_SESSION_TOKEN`.
Bind is always `127.0.0.1`, with request logging disabled. `--allow-origin` accepts
the exact frontend origin; browser origins are denied by default. Health uses
`GET /api/health` with `Authorization: Bearer ...`. `/ws?token=...` accepts the
unchanged v1 `text.input`, `confirm.response`, `task.cancel` and `tts.stop` events.
Wrong credentials/origins/versions are rejected; only one connection owns local
execution. Disconnect cancels active work before releasing ownership.

`LocalSession` routes direct user text through the keyword matcher into
`PlanExecutor`. Unknown/ambiguous commands produce a reply/question without an
automatic upload. Stop/cancel controls remain local. An explicitly assembled
cloud flow can be invoked through `request_cloud`; it still applies C3's payload
approval and policy checks. C6 connects its validated plan outcomes to the same
executor with owned cancellation/replacement and independent action confirmations;
see CLOUD_EXECUTION.md. The supplied local CLI disables cloud use entirely.
The existing voice echo server remains separate. The frontend owns its actual
buttons, captions and activity view; it can use `local_command_execution` in
the mock and the real local text service for its handoff tests.

## Execution guarantees and limits

`PlanExecutor` implements the `ExecutionEngine` boundary and accepts a `ToolRunner`.
It copies/revalidates plans through C1, rejects unknown tools/invalid arguments,
asks for clarification before low-confidence/incomplete plans, and checks
registered policy before preview and execution. Each risky step requires its
own correlated, single-use confirmation with a click or key. Voice alone,
wrong IDs, stale responses and declines cannot authorize it. A conservative
plan requesting extra confirmation is also respected. Future risky tool dry runs
must explicitly describe all destinations, recipients and side effects; no real
send/delete/write tool is shipped by this work.

Local steps do not probe connectivity. Network-dependent steps recheck it and
stop honestly when offline; C4 does not pretend to queue mail. Outbox/idempotency
and irreversible provider operations remain Phase F work. C5 adds validated
earlier-result bindings for dependent steps; see STEP_RESULTS.md for grammar,
template checks, typed resolution and confirmation/copy guarantees.

Every tool/dry run has its declared timeout. The production runner uses a fresh
Python worker process with private stdio, bounded job/result sizes, suppressed
tool stdout/stderr and sanitized failures. On timeout/cancel it terminates and
awaits the worker, escalating to kill if necessary. A timed-out thread cannot
continue executing in the background. Tool runs are not automatically retried.
Workers do not inherit ARIA/GATEWAY environment credentials.

This is not a security sandbox: registered tools, their validators and modules
are trusted application code. Worker pickle data is created only by the trusted
parent from registry instances; it must never be accepted over HTTP/WebSocket or
from model output. Tools must be importable/pickleable; process startup is part
of their timeout. Packaged sidecars will need a worker entrypoint in Phase I.

Cancellation cannot undo completed actions or retract an external effect already
started. Activity records completed steps and reports uncertainty for an interrupted
step; it never claims rollback. Failures/declines stop all later steps. Results
are validated before success and caption events are emitted.

Activity is currently session `activity.entry` events, not durable per-user
history; profile-bound persistence remains identity/integration work. Captions
use `spoken:false`; no speech models or microphones are opened by this service.

## Local calendar behavior

`cal.list` is read-only (`risk=none`), unlike future calendar create/move/cancel
tools. It reads at most 2 MiB of the explicitly configured ICS, expands recurrences,
honors exclusions and cancelled instances, and filters overlaps in the configured
timezone, including all-day events. It never saves the calendar or fetches remote
URLs/attachments. Missing/malformed files fail rather than claim an empty calendar.
Limits are 1,000 series/expanded occurrences, no secondly/minutely recurrence,
and the worker timeout. Unsupported/oversized calendars report failure; no events
are silently dropped to fit a result.

## Verification

Unit tests keep sockets blocked and use memory runners/stub app launchers plus
fictional ICS files. They cover confirmation/decline/replay, policy mutation,
timeout/cancel, no late steps, input/output validation, network gating, recurrence,
timezone boundaries and exact real-session/mock event flow.

`python scripts/smoke_execution.py` separately checks actual process execution,
dry-run stdout suppression, timeout and cancellation using only its own temporary
markers. It never opens an app, reads credentials or contacts a service. CI runs
it on Linux, Windows and macOS. Real Windows application/UI performance and a
non-technical staff smoke test remain acceptance checks, not claims from stubs.
