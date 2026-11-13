# E2E scenarios

Each file is used three ways: by the mock agent (frontend development), by the backend e2e tests, and by Playwright. See docs/TESTING.md section 8.3 for the full list of scenarios (E2E-01 to E2E-15). Add a file here before building any user-visible feature.

Format: `{"name": "...", "description": "...", "steps": [...]}`. A step is either
`{"send": <agent event>, "delay_ms": n}` or
`{"wait_for": "<ui event type>", "match": <complete UI event example>}`.
Events must match docs/API_CONTRACT.md and include `v: 1`. Delays must be
nonnegative integer milliseconds, at most 60,000; omitted delays are zero.
Unknown steps/event names and invalid examples are rejected before replay.

`match` is required for approval and confirmation steps and must refer to a
preceding request's ID with `decision: "yes"`. Other waits may omit it for
interactive use; committed automated handoff fixtures provide complete examples.
Responses with other IDs do not advance the replay. A matching `no` or a
`task.cancel` ends it without later success events. Click and key are both
accepted for confirmation. The mock never performs real actions.

See [the frontend handoff](../../../docs/FRONTEND_HANDOFF.md) for token setup,
generated TypeScript types and scenario playback instructions.
