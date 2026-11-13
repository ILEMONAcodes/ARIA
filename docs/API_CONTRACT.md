# API contract: UI and agent

Owner: backend and AI engineer. The frontend engineer must approve any change. The source of truth is the Pydantic models in `services/agent/src/agent/contracts`. Generated JSON Schema lives in `apps/desktop/src/contract/schema.json`; run `python scripts/gen_contract.py` after any change.

The UI never talks to the language model, the microphone or the files directly. It talks only to the local agent.

- **Transport:** WebSocket at `ws://127.0.0.1:<port>/ws?token=<session token>` for events, plus a small REST API under `/api` for settings and lists. The backend binds to localhost only. The Tauri shell starts the agent and passes the token.
- **Audio:** the agent captures the microphone and plays the voice itself. The UI shows captions and status only.
- **Source of truth:** Pydantic models in `services/agent/src/agent/contracts`. A script generates JSON Schema and TypeScript types into `apps/desktop/src/contract`. CI fails if the generated files are out of date.
- **Versioning:** every message has `v` (integer). Adding a field is fine. Renaming or removing one needs a version bump and a note in DECISIONS.md.

## Events from agent to UI

- `status` { state: idle | listening | thinking | working, online: bool, profile: hosted | local }
- `transcript.partial` { text }
- `transcript.final` { text, speaker: { id, name, confidence } }
- `speaker.confirm_request` { name } (low-confidence match, ID-2)
- `plan.preview` { task_id, summary }
- `cloud.approval_request` { approval_id, payload_preview } (exactly what will be sent)
- `confirm.request` { confirm_id, task_id, risk, dry_run_text, details: { recipients, subject, attachments }, needs_click: bool }
- `reply.text` { task_id, text, spoken: bool }
- `result.answer` { text, citations: [ { doc, page, date, passage, file_path } ] }
- `result.document` { path, title }
- `outbox.update` { items: [ { id, status, to, subject, attempts } ] }
- `activity.entry` { id, ts, text, undoable }
- `error` { code, message }

## Events from UI to agent

- `ptt.start`, `ptt.stop`
- `text.input` { text } (typed correction)
- `confirm.response` { confirm_id, decision: yes | no, via: click | key }
- `approval.response` { approval_id, decision }
- `speaker.confirm_response` { accept }
- `task.cancel` { task_id }
- `tts.stop`
- `activity.undo` { id }
- `source.open` { file_path, page }

## REST

- `GET/PUT /api/settings`
- `POST /api/profiles/enroll/start`, `POST /api/profiles/enroll/sample`, `DELETE /api/profiles/{id}`
- `GET /api/library/status`
- `GET /api/outbox`, `DELETE /api/outbox/{id}`
- `GET /api/activity`
- `GET /api/health`

## Mock agent

The frontend must never wait for the backend. `services/agent/src/agent/mock` starts a fake agent that replays scenario files from `tests/e2e/scenarios`. Run it with `python -m agent.mock --scenario policy_question`. Every real feature gets a scenario file before it is built, so both sides agree on the events.
