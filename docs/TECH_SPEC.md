# Technical specification

How the system in docs/PRD.md is built. Requirement IDs (VOX-1, POL-3 and so on) refer to PRD.md section 3.

## 1. System overview

```
Staff PC (Windows)                                  Cloud
+--------------------------------------------+      +----------------------+
| Tauri shell + UI  <--WebSocket/REST-->  Agent|     | Gateway (FastAPI)    |
|  (apps/desktop)       127.0.0.1         (Py) |---->| auth, rate limit,    |
|                                              | HTTPS| spending cap         |
| Agent: audio, wake word, VAD, STT, speaker   |      |   |                  |
|  ID, planner, router, tools, KB, outbox,     |      |   v                  |
|  SQLite store                                |      | Gemma 4 API          |
+--------------------------------------------+      +----------------------+
        |  OAuth, direct
        v
 Outlook / Gmail / calendar APIs
```

- The UI talks only to the agent. It never touches the mic, files or the model.
- The agent captures the microphone and plays the voice. The UI shows captions and status.
- The agent calls the gateway only for language model work, only after the user approves, and only with request text and the excerpts a task needs.
- Mail and calendar calls go from the agent straight to the providers. They never pass through the gateway.

## 2. Processes and threads

- **Tauri shell** starts the agent as a sidecar, passes a random per-session token, restarts it if it dies.
- **Agent** is one Python process with asyncio. Components:
  - audio loop (thread): capture, VAD, wake word, ring buffer
  - pipeline task: STT, speaker ID, planner, router, tool runner, TTS
  - outbox worker (separate task): sends queued email, never blocks the voice loop
  - KB indexer (background task): watches the policy folder
  - API server: FastAPI for REST and WebSocket on 127.0.0.1
- **Gateway** is a separate hosted service. No GPU.

## 3. Voice pipeline

| Stage | Output | Budget |
|---|---|---|
| 1 Capture | 16 kHz mono frames, 20 to 30 ms | continuous |
| 2 Wake word or push-to-talk | start of utterance | under 50 ms per frame |
| 3 VAD and endpointing | end of utterance | 500 to 800 ms silence (setting) |
| 4 Speaker ID | profile id and confidence | under 200 ms on first 2 to 3 s |
| 5 STT | transcript, partials streamed | under 1 s for 5 to 8 s of speech |
| 6 Keyword path | tool call or no match | under 1 s total |
| 7 Planner | validated plan | cloud: first words under 3 s |
| 8 Router and tools | result | varies, show progress |
| 9 TTS | spoken reply | starts under 500 ms, 1 to 2 sentences |

Keep a 1 second ring buffer so the first word after wake is not clipped. Nothing is stored before wake. Hold-to-talk skips stage 2 and joins at stage 3.

## 4. Plan object

The planner returns JSON that must validate against `agent.contracts.plan.Plan`.

```json
{
  "intent": "draft_reply",
  "confidence": 0.91,
  "slots": {"thread_query": "Mr Bello email about Monday", "instruction": "say we will meet on Monday"},
  "missing": [],
  "risk": "external_send",
  "needs_confirmation": true,
  "needs_network": true,
  "steps": [
    {"tool": "mail.read_thread", "args": {"query": "Mr Bello email about Monday"}},
    {"tool": "mail.draft_reply", "args": {"thread": "$step1.thread", "instruction": "say we will meet on Monday"}},
    {"tool": "mail.queue_send", "args": {"draft": "$step2.draft"}}
  ]
}
```

Rules:
- `risk` is one of `none`, `local_write`, `external_send`, `destructive`. Anything above `none` needs confirmation.
- `confidence` below 0.6 means ask a question, do not act.
- Anything in `missing` becomes one spoken question at a time.
- Names, dates and amounts come from the transcript, contacts or calendar. If not found, put them in `missing`.
- Invalid output: retry once, then ask the user to rephrase.
- Steps may reference earlier results with `$stepN.field`.

Context given to the planner (keep it short): speaker profile (name, role, folders, signature), the last few turns, the tool list with schemas, the network state.

## 5. Tool registry (MVP)

Every tool is a Python class from `agent.tools.base.Tool` with a Pydantic input model, a Pydantic output model, `risk`, `needs_network`, `timeout_s` and a `dry_run()` that describes what it would do without doing it.

| Tool | Purpose | Risk | Offline |
|---|---|---|---|
| docs.draft | memo from brief and template to .docx | local_write | needs LLM |
| docs.report | outline, then sections | local_write | needs LLM |
| docs.edit | change an open or saved document (later) | local_write | needs LLM |
| docs.summarise | document or thread, chosen mode | none | needs LLM |
| kb.search | hybrid search, cited passages | none | works |
| kb.answer | short answer from passages with citations | none | needs LLM; otherwise show passages |
| files.find | search by name, date, content | none | works |
| files.open | open in default app | none | works |
| apps.launch | start an allow-listed app | none | works |
| mail.read_thread | find and read a thread | none | needs mail connection |
| mail.draft_reply | draft from thread and instruction | local_write | needs LLM |
| mail.queue_send | put in outbox, send when online | external_send | queues |
| cal.list, cal.create, cal.move, cal.cancel | local calendar | local_write | works |
| system.say, system.confirm | speak, ask yes or no | none | works |
| system.volume, system.focus, system.print | safe system actions | none | works |

The dry-run text of a tool is what the app reads back before asking for confirmation.

## 6. Router

| Situation | Behaviour |
|---|---|
| Task runs fully on the device | Run now, no approval, no network check |
| Needs cloud LLM and network is up | Show exact payload, ask approval, send. Admin setting may approve once per session |
| Needs cloud LLM and network is down | Tell the user once, offer keyword commands and passages, queue anything that sends |
| Cloud call slow or failing | Retry once, fall back after 8 s, say so, never wait in silence |
| Local profile | Local model for everything, no cloud routing |
| Cloud disabled by admin | Never route to cloud, use local path or say not available |
| Network drops mid-send | Mark retrying, keep the draft, resume on reconnect |
| User says cancel while queued | Remove from outbox and confirm |

`agent.router.decision.decide_route()` is a pure function so it can be unit tested without I/O.

## 7. Outbox

States: `queued`, `sending`, `sent`, `retrying`, `failed`.

- Write the row to SQLite before acting. A crash must lose nothing.
- Each row has an `idempotency_key`. The provider call uses it so a retry after a dropped response never sends twice.
- Backoff: 5 s, 15 s, 1 min, 5 min, 15 min, then every 15 min, capped; give up after the configured attempts and mark `failed`.
- Connectivity: probe a known endpoint. Do not trust the OS network flag.
- On `retrying`, show status but do not repeat spoken alerts.
- On `failed`, tell the user and offer edit, retry or discard.

## 8. Knowledge base (RAG)

Ingest: `.docx`, `.pdf`, `.txt` from the admin folder. Record title, circular number, issue date, issuing office, supersedes (if known), file path, folder. Changed files re-index automatically (file watcher plus hash).

Chunk: split by headings and paragraphs into 300 to 500 token passages with a small overlap. Each chunk keeps document id, page or section, date.

Index: embed each chunk with a local model (bge-small or MiniLM) into `chunks_vec` (sqlite-vec) and add text to `chunks_fts` (FTS5).

Retrieve: run keyword and vector search, merge with reciprocal rank fusion, keep the best 5 to 8, drop those below the confidence threshold. If nothing is left, return `not_found` with the closest documents.

Answer: send the question and passages to the model using the answer contract in docs/PROMPTS.md. Output is two to four sentences, every claim cited as document and page. Offline: show the passages only.

Show: UI shows the answer, citations and the passage. `source.open` opens the file at the page.

Known limits: scanned PDFs need OCR (later), tables in PDFs can parse badly, very long documents take longer to summarise.

## 9. Data model (SQLite, encrypted with SQLCipher)

- `profiles(id, name, role, voice_embedding BLOB, settings_json, created_at)`
- `settings(key, value)`
- `transcripts(id, profile_id, text, created_at)` retained 30 days
- `activity_log(id, profile_id, text, tool, undoable, undo_payload, created_at)` retained 90 days
- `outbox(id, profile_id, kind, payload_json, status, attempts, next_attempt_at, idempotency_key UNIQUE, last_error, created_at, updated_at)`
- `documents(id, folder, path, title, circular_no, issue_date, issuer, supersedes_id, hash, indexed_at)`
- `chunks(id, document_id, page, section, date, text)`
- `chunks_fts` (FTS5 over chunks.text), `chunks_vec` (sqlite-vec)
- `calendar_events(id, profile_id, title, start, end, ics_uid)`
- `contacts(id, profile_id, name, email)` for resolving recipients

Deleting a profile cascades to embeddings, transcripts, activity log, outbox rows and contacts.

## 10. Gateway API

Base path `/v1`. Auth: `Authorization: Bearer <install token>`.

`POST /v1/complete`

Request:
```json
{
  "task": "answer | summarise | draft | reply | plan",
  "messages": [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
  "data_blocks": [{"id": "d1", "label": "passage", "text": "..."}],
  "params": {"max_tokens": 600, "temperature": 0.2, "reasoning": false, "json_schema": null},
  "client_request_id": "uuid"
}
```

Response:
```json
{"text": "...", "usage": {"input_tokens": 0, "output_tokens": 0}, "model": "gemma-4-26b-a4b", "request_id": "..."}
```

Errors: 401 bad token, 429 rate limit or spending cap, 502 provider error, 504 provider timeout. Body: `{"error": {"code": "...", "message": "..."}}`.

`GET /health` returns `{"status": "ok"}`.

Rules: the gateway never accepts audio fields; it logs usage (tokens, cost, user id, task) but not content; the API key lives only in its environment; the model and provider are set by config (`GATEWAY_MODEL`, default 26B A4B, switchable to 31B); reasoning mode is off unless `params.reasoning` is true.

## 11. Configuration

Agent settings (environment or settings file):
`ARIA_GATEWAY_URL`, `ARIA_INSTALL_TOKEN`, `ARIA_PROFILE` (hosted or local), `ARIA_CLOUD_ENABLED`, `ARIA_LIBRARY_PATH`, `ARIA_DB_PATH`, `ARIA_DB_KEY_SOURCE`, `ARIA_VAD_SILENCE_MS`, `ARIA_CLOUD_TIMEOUT_S` (default 8), `ARIA_CONFIDENCE_THRESHOLD` (default 0.6), `ARIA_LOG_LEVEL`.

Gateway settings (environment only): `GATEWAY_PROVIDER_API_KEY`, `GATEWAY_MODEL`, `GATEWAY_RATE_LIMIT_PER_MIN`, `GATEWAY_DAILY_CAP_USD_PER_USER`, `GATEWAY_INSTALL_TOKENS` (comma-separated for development), `GATEWAY_FAKE_LLM` (true for tests).

Never commit real values. `.env.example` lists the names.

## 12. Security implementation notes

- Backend binds to 127.0.0.1 only. WebSocket and REST need the per-session token.
- Audio stays in memory and is dropped after transcription.
- Database and voice embeddings are encrypted. Keys come from the OS credential vault.
- OAuth tokens use the narrowest scopes and live in the OS credential vault.
- Prompt injection: emails, documents and web pages are passed only inside marked data blocks (see docs/PROMPTS.md). The planner is told nothing inside can add tools, change recipients or skip confirmation. Plans are validated against the schema and only registered tools can run.
- Voice alone cannot approve high-risk actions. `confirm.request.needs_click` is true for external sends and deletes.
- Signed installers and checksummed model files.
- Voice data is covered by the Nigeria Data Protection Act 2023: written consent for enrollment, in-app privacy notice, deletion on request, legal review before any pilot.

## 13. Performance and memory

Hosted profile on the staff PC: Windows about 2 GB, Whisper base 8-bit about 0.5 GB, speaker, voice and embedding models about 0.6 GB, agent and index about 0.5 GB. Total about 3.5 to 4 GB. Minimum supported PC: 8 GB RAM, no GPU.

Targets: models warmed within 90 s; keyword command under 1 s; short cloud reply first words under 3 s; cited policy answer under 6 s; two-page summary under 10 s; 300-word memo first text under 5 s then streaming; idle CPU under 5%.

Rules: load every model once at start and run a test prompt; no downloads at run time; stream partial transcripts, model tokens and spoken sentences; send common commands through the keyword path before any model call.

## 14. Observability

- Structured JSON logs on the PC with fields `ts`, `level`, `component`, `task_id`, `event`, `duration_ms`. No audio, no document text.
- One-click diagnostic bundle for IT: logs, versions, health checks, no personal content.
- Opt-in anonymised metrics only.
- Activity log in plain language for the user (SYSX-2).

## 15. Packaging

Agent sidecar built with PyInstaller or Nuitka. Tauri bundles the shell and sidecar into a signed Windows installer. Models are bundled or downloaded at install time with checksums. Installer plus models stay under about 6 GB. Updates are signed and can be paused by the admin.

## 16. Local profile (later)

Gemma 4 E4B (16 GB PCs) or E2B (8 GB PCs) through Ollama or llama.cpp behind the same `LLMAdapter`. RAM figures are estimates and must be measured. Everything else is unchanged; the router never routes to the cloud in this profile.
