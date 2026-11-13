# Role: backend and AI engineer

You own `services/agent`, `services/gateway`, the contract models, `library/`, `tests/audio_fixtures` and `tests/kb_questions`. Read AGENTS.md, docs/PRD.md and docs/TECH_SPEC.md first. Prompts are in docs/PROMPTS.md. Work through the phases in order; do not start one until the previous "done when" passes. Phase order and gates are also in docs/ROADMAP.md.

Do the phases in order. Do not start one until the previous "done when" passes.

## Phase A: Foundations
Requirement IDs: DEP-1, DEP-4
- Create the repo, Python project (uv or poetry), ruff, mypy, pytest, pre-commit.
- Settings loader (environment plus settings file), logging in JSON.
- `store`: SQLite with migrations, SQLCipher encryption, retention purge (30 days transcripts, 90 days activity log).
- Interfaces for every module, plus fake implementations.
- `contracts` package and the type generation script.
- Mock agent serving the first scenario file, so the frontend can start.
- Done when: CI is green on an empty feature, the mock agent runs, generated TypeScript types compile.

## Phase B: Voice loop (works with the network off)
Requirement IDs: VOX-1 to VOX-4, SYSX-1
- Audio capture (sounddevice, 16 kHz mono, 20 to 30 ms frames), mic selection.
- Silero VAD with endpointing (500 to 800 ms silence, a setting).
- openWakeWord with a custom "HeyAria" model, 1 second ring buffer, nothing stored before wake.
- faster-whisper wrapper (tiny.en or base.en, 8-bit), custom vocabulary, partial results streamed.
- Piper text-to-speech, sentence-by-sentence streaming, barge-in ("stop").
- Push-to-talk path feeding the same pipeline from VAD onward.
- WER benchmark script on the Nigerian-accent test set (100 to 200 recorded sentences).
- Done when: a spoken sentence becomes a spoken echo with the network disabled, transcript under 1.5 s, WER logged.

## Phase C: Planner, gateway and router
Requirement IDs: DEP-3, DEP-4, SYS-1, CAL-1, SYSX-3
- Plan schema (intent, confidence, slots, missing, risk, needs_confirmation, needs_network, steps).
- Tool registry and base class (schemas, risk, timeout, dry-run).
- Keyword fast path with rapidfuzz: open, find, calendar, cancel.
- `LLMAdapter` with a gateway client and a fake client. Retry once, fall back after 8 seconds, never wait in silence.
- `services/gateway`: FastAPI, per-install auth, rate limit, per-user spending cap, usage logging, calls Gemma 4 26B A4B. Config switch for 31B. Reasoning mode off for short commands.
- Router: local runs immediately; cloud shows the exact payload and waits for approval; offline tells the user once and queues; Local and admin-disabled profiles never route to cloud.
- Confirmation flow with dry-run text.
- Done when: "Open Excel" and "What is on my calendar today?" work offline under 1 s; a cloud task shows an approval request, runs through the gateway and returns text; killing the gateway triggers the fallback message.

## Phase D: Knowledge base (policy search)
Requirement IDs: POL-1 to POL-5
- Ingest .docx, .pdf, .txt with title, circular number, issue date, page or section.
- Chunk 300 to 500 tokens with small overlap, keep page and date.
- Local embeddings (bge-small or MiniLM), SQLite FTS5 plus sqlite-vec, merge results, keep best 5 to 8, drop low-confidence.
- Answer contract prompt: use only supplied passages, cite document and page, say "not found" and list closest documents when passages do not answer, flag conflicts by date.
- Without the model (offline), show passages only.
- Sample library: 8 to 12 public circulars plus 3 fictional internal ones.
- 30-question golden set (20 answerable, 10 not) with expected citations and a scoring script.
- Done when: the golden set scores 90% or higher on correct answer, correct citation and correct "not found". Record chunk size and passage count in DECISIONS.md.

## Phase E: Documents, reports and summaries
Requirement IDs: DOC-1, DOC-2, RPT-1, RPT-2, SUM-1 to SUM-3
- `docs.draft`: memo from a spoken brief into .docx with a template (python-docx), one clarifying question when something is missing, save to the user's folder with topic and date in the name.
- `docs.report`: outline first, user approval, then section by section; redo one section.
- `docs.summarise`: one line, five bullets, one page, for documents and email threads, with page or heading references.
- Faithfulness check: every number, date and proper noun in a summary must appear in the source; flag the rest before showing.
- Done when: a memo opens in Word with correct styles; 9 of 10 reviewed summaries have no invented facts.

## Phase F: Mail, calendar and outbox
Requirement IDs: MAIL-1 to MAIL-3, REPLY-1 to REPLY-3, CAL-2, SYS-2, SYS-3, SYSX-2
- Microsoft Graph and Gmail clients (OAuth, narrowest scopes, tokens in OS credential vault), test inbox for development.
- Find thread by description, draft reply with tone and signature, read-back, explicit yes before send, flag reply-all and external recipients.
- Attach by description with a question when more than one file fits.
- Outbox: write to SQLite before acting, idempotency key, states queued, sending, sent, retrying, failed, exponential backoff, connectivity probe to a real endpoint, worker separate from the voice loop.
- Local calendar (ICS): list, create, move, cancel with conflict check.
- File finder (name, recency, content index) and app launcher on an allow-list. System actions limited to volume, window focus and print.
- Activity log with undo where possible.
- Done when: a reply is drafted from a thread, confirmed, queued with the network off, and sent exactly once when it returns.

## Phase G: Speaker ID and profiles
Requirement IDs: ID-1 to ID-5
- SpeechBrain ECAPA-TDNN embeddings, 30-second enrollment, encrypted storage, cosine similarity, low-confidence confirmation.
- Per-user settings (folder, signature, default sender, tone). Profile delete removes embeddings, history and queued items.
- Voice alone never approves a send or delete; `needs_click` is true for high-risk actions.
- Done when: two or three people are recognised and get their own settings; accuracy measured on held-out enrollment clips.

## Phase H: Evaluation, safety and model choice
- Run the same 30 tasks (memos, summaries, replies, policy questions) on Gemma 4 26B A4B and 31B, and on two providers if needed. Compare quality, speed and cost. Record the result in DECISIONS.md.
- Prompt-injection corpus: 10 or more malicious email bodies and documents. The agent must not add tools, change recipients or skip confirmation.
- Latency benchmarks against PRD section 6 targets on a real 8 GB staff PC.
- Check the chosen provider's data terms and record them.
- Done when: eval results are in DECISIONS.md and every PRD speed target is measured.

## Phase I: Packaging (shared with frontend)
Requirement IDs: DEP-1, DEP-2
- Package the agent as a sidecar (PyInstaller or Nuitka). Bundle Whisper, speaker, embedding and Piper models with checksums.
- Models load once at start and a test prompt runs before the first request.
- Done when: a clean Windows machine installs the app and it starts with the network off, ready in under 90 seconds.
