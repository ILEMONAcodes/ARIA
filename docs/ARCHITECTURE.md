# Backend and AI file architecture

This is the implementation map for `agents/backend-ai.md`, phases A to I.
Requirements and phase gates remain in PRD.md and ROADMAP.md. API_CONTRACT.md
defines the UI boundary; this document does not change that contract.

`[existing]` means a file or package is present in the working tree. It does not
mean the feature is complete. `[planned X]` means create it during phase X,
after the preceding gate passes. Planned package names are internal choices;
record significant changes in DECISIONS.md. Do not create empty implementations
or claim completion just because a directory exists.

## Runtime boundaries

The desktop shell starts one Python agent on the staff PC. The agent owns the
microphone, speech models, speaker identification, files, local search, calendar,
encrypted database and outbox. The React UI communicates only through the
authenticated localhost WebSocket and REST contract.

The agent sends approved request text and selected excerpts to the cloud
gateway over HTTPS. Audio, credentials and the whole library stay on the PC.
The gateway owns the model API key, installation authentication, rate limits,
spending limits and provider adapter. Mail OAuth calls go directly from the
agent to the mail provider.

The request path is capture, endpoint detection, transcription, speaker check,
keyword matching, planning, schema validation, routing, required approvals,
registered tools, activity recording and spoken/on-screen results. The model
only proposes plans. The application validates and executes them.

## Repository map

```text
ARIA/
├── AGENTS.md                         [existing] repository rules
├── agents/
│   ├── backend-ai.md                 [existing] backend phases and gates
│   └── frontend.md                   [existing] frontend ownership
├── docs/
│   ├── ARCHITECTURE.md               this implementation map
│   ├── PRD.md                        [existing] requirement IDs
│   ├── TECH_SPEC.md                  [existing] technical behavior
│   ├── API_CONTRACT.md               [existing] UI/agent messages
│   ├── FRONTEND_HANDOFF.md           [existing] generated types and authenticated mock setup
│   ├── ROADMAP.md                    [existing] shared phase gates
│   ├── TESTING.md                    [existing] required tests and evaluations
│   ├── CICD.md                       [existing] CI and release policy
│   ├── PROMPTS.md                    [existing] model prompt rules
│   └── DECISIONS.md                  [existing] decisions and discoveries
├── pyproject.toml                   [existing] uv workspace and dev tools
├── uv.lock                          [existing] locked Python dependencies
├── .python-version                  [existing] development Python version
├── .pre-commit-config.yaml          [existing] required backend checks
├── .env.example                     [existing] variable names, no secrets
├── .github/workflows/               [existing] CI/release scaffolding
├── config/agent.example.toml        [existing] credential-free settings example
├── apps/desktop/                    [existing] frontend-owned scaffold
│   └── src/contract/                 [existing] generated JSON Schema and TypeScript
├── services/agent/                  staff PC service; detailed below
├── services/gateway/                cloud service; detailed below
├── library/                         [existing] sample library scaffolding
├── scripts/
│   ├── gen_contract.py              [existing] JSON Schema generation
│   ├── check_backend.py             [existing] shared local/CI check command
│   ├── contract/                    [existing] pinned generator, TS compiler and consumer checks
│   ├── smoke_mock.py                [existing] separate live localhost integration check
│   ├── benchmark_wer.py             [planned B] transcription accuracy
│   ├── evaluate_kb.py               [planned D] golden-set scoring
│   └── benchmark_latency.py         [planned H] PRD speed measurements
└── tests/
    ├── audio_fixtures/              [existing] fixture instructions; clips needed
    ├── kb_questions/                [existing] partial golden-set scaffold
    ├── injection/                   [planned H] malicious fictional data
    ├── evals/                       [planned H] model/provider comparison
    └── e2e/
        ├── scenarios/               [existing] four starter scenario files
        ├── agent/                   [existing] placeholder; tests needed
        └── ui/                      [existing] frontend-owned placeholder
```

## Local agent package

```text
services/agent/
├── pyproject.toml                   [existing] package and test configuration
├── src/agent/
│   ├── __init__.py                  [existing]
│   ├── __main__.py                  [existing] foundation checks and lifecycle CLI
│   ├── bootstrap.py                 [existing] dependency assembly/lifecycle
│   ├── config.py                    [existing] validated file/env settings
│   ├── logging_config.py            [existing] structured JSON logs
│   ├── interfaces/                  [existing] protocols and shared value types
│   ├── fakes/                       [existing] deterministic in-memory test adapters
│   ├── contracts/                   [existing] public Pydantic contracts
│   │   ├── events.py                [existing] UI and agent events
│   │   └── plan.py                  [existing] plan and risk schema
│   ├── mock/                        [existing] scenario-driven fake server
│   │   ├── __main__.py              [existing] mock CLI
│   │   ├── server.py                [existing] replay and validation
│   │   └── scenarios.py             [existing] typed fixture and response validation
│   ├── api/                         [planned B] real-agent localhost transport and voice events
│   ├── store/                       [existing] encrypted persistence boundary
│   │   ├── database.py              SQLCipher connections and transactions
│   │   ├── local.py                 lifecycle adapter; open/purge/close
│   │   ├── migrations/              ordered schema migrations
│   │   ├── repositories.py          persistence operations
│   │   └── retention.py             30-day transcripts; 90-day activity
│   ├── security/keys.py             [existing] native vault and key-provider interface
│   ├── audio/                       [planned B] capture, VAD, wake word, buffers
│   ├── stt/                         [planned B] faster-whisper adapter
│   ├── tts/                         [planned B] Piper adapter and interruption
│   ├── voice/                       [planned B] voice-loop orchestration/PTT
│   ├── planner/                     [planned C] keyword path and plan validation
│   ├── llm/                         [planned C] gateway adapter and fake adapter
│   ├── router/
│   │   ├── decision.py              [existing] pure route decision
│   │   └── executor.py              [planned C] approved execution/cancellation
│   ├── tools/
│   │   ├── base.py                  [existing] Tool interface and registry
│   │   ├── apps.py                  [planned C] allow-listed app launching
│   │   ├── calendar.py              [planned C/F] listing, then confirmed changes
│   │   ├── knowledge.py             [planned D] policy retrieval/answer tools
│   │   ├── documents.py             [planned E] memo/report/summary tools
│   │   ├── mail.py                  [planned F] read, draft and confirmed queue
│   │   ├── files.py                 [planned F] local file search/open
│   │   └── system.py                [planned F] volume, focus and print
│   ├── confirmations/               [planned C] payload/action approval state
│   ├── kb/                          [planned D] ingestion, indexing, retrieval
│   ├── documents/                   [planned E] templates, drafting, summaries
│   ├── mail/                        [planned F] Graph/Gmail OAuth adapters
│   ├── outbox/                      [planned F] durable queue/retries/idempotency
│   ├── calendar/                    [planned C/F] local ICS adapter
│   ├── files/                       [planned F] filename/content index
│   ├── activity/                    [planned F] user-readable history and undo
│   └── identity/                    [planned G] enrollment, matching, profiles
├── tests/unit/                      [existing] contracts, config, logs, mock, router, tools
└── packaging/                       [planned I] Windows sidecar build inputs
```

Adapters implement interfaces; orchestration receives interfaces through
bootstrap.py. Interfaces cover SpeechToText, SpeakerIdentifier, Planner, Tool,
LLMAdapter, speech output, audio input, storage, credentials and network access.
Native model libraries are loaded by their adapters, not imported by contracts
or pure decision functions. Unit tests use fakes and block network sockets.

The store must require SQLCipher encryption for user data and fail explicitly
when encryption/key access is unavailable. Never silently substitute plaintext
SQLite. Keys and OAuth credentials come from the OS credential vault. Fakes use
fictional records and temporary storage.

Each tool declares its input/output models, risk, network requirement, timeout
and dry run. The executor enforces these declarations independently of model
output. Every risk above `none` requires confirmation; external sends and
deletes require a click or keypress. Only approved payloads reach the gateway.

## Cloud gateway package

```text
services/gateway/
├── pyproject.toml                   [existing]
├── Dockerfile                      [existing] starter image definition
├── src/gateway/
│   ├── __init__.py                  [existing]
│   ├── main.py                      [existing] FastAPI/auth/limits skeleton
│   ├── config.py                    [existing] environment settings skeleton
│   ├── llm.py                       [existing] protocol, fake, provider placeholder
│   ├── auth.py                      [planned C] installation authentication
│   ├── limits.py                    [planned C] rate/spending enforcement
│   ├── usage.py                     [planned C] content-free usage records
│   └── providers/                   [planned C] chosen Gemma provider adapter
└── tests/unit/                     [existing] 9 starter tests
```

The existing gateway is scaffolding: the real provider call is not implemented,
and its in-memory counters are not production spending enforcement. Provider
selection follows evaluation and data-term checks; do not treat starter price
constants or model labels as verified provider capabilities.

## Implementation order and gates

| Step | Work and requirement IDs | Completion evidence |
| --- | --- | --- |
| A1 | Workspace, lockfile, lint/types/tests, pre-commit and CI; DEP-1, DEP-4 foundation | A fresh locked install runs the shared backend checks |
| A2 | Agent file/env settings and JSON logs | Valid/invalid settings, precedence and content-safe log tests |
| A3 | SQLCipher store, migrations, key interface and retention | Encryption, migration, transaction and retention tests |
| A4 | Module interfaces, fakes and dependency assembly | Deterministic fake adapters work with network blocked |
| A5 | Contract generation and mock-agent handoff | Mock scenario runs; generated TypeScript compiles; CI green |
| B | Offline capture, VAD, wake, STT, TTS, PTT and stop; VOX-1–4, SYSX-1 | Spoken echo offline; transcript under 1.5 seconds; WER recorded |
| C | Plans, tools, keywords, gateway, routing, approvals and cancel; DEP-3–4, SYS-1, CAL-1, SYSX-3 | Local commands under 1 second; approved cloud request works; gateway failure falls back |
| D | Ingest, chunk, hybrid retrieval, citations, offline passages, samples and golden set; POL-1–5 | At least 90% correct answers/citations/not-found across 30 questions |
| E | Memo templates/save, report outlines/sections, summary modes and faithfulness; DOC-1–2, RPT-1–2, SUM-1–3 | Memo opens correctly in Word; 9 of 10 reviewed summaries contain no invented facts |
| F | Mail OAuth, reply/read-back/attachments, outbox, ICS changes, files/system tools, history/undo; MAIL-1–3, REPLY-1–3, CAL-2, SYS-2–3, SYSX-2 | Confirmed reply survives offline/crash/reconnect and sends exactly once |
| G | Consent, enrollment, encrypted embeddings, speaker matching, profile settings/delete; ID-1–5 | Two or three users recognized; held-out accuracy measured; voice cannot approve sends/deletes |
| H | Model/provider comparison, malicious-data corpus, privacy terms and latency; PRD sections 4, 6 and 7 | Results and provider terms recorded; all PRD speed targets measured on staff hardware |
| I | Sidecar, bundled/checksummed models, warmup and signed installer; DEP-1–2 | Clean Windows PC installs and starts offline, ready within 90 seconds |

A1–A4 have passing hosted backend and Windows/macOS checks. A5 is implemented
with 156 Python unit tests, two generator tests, strict TypeScript compilation,
all four mock replay tests, and a successful live localhost policy replay.
A5's hosted CI passed: backend checks, the live localhost policy replay, strict
TypeScript generation/consumer checks, and Windows/macOS mock/startup tests.
The backend role's Phase A foundation gate is passed on the handoff branch;
the work remains in draft PRs for review and is not merged or deployment-ready.

Generated TypeScript lives alongside the JSON Schema. A separate tool package
under scripts/contract verifies the types without building the frontend-owned
app. FRONTEND_HANDOFF.md documents setup, auth, imports and response examples.
The mock requires the documented session token and stops on decline/cancel;
it still never runs tools, reads real files or contacts a model/mail provider.

The real CLI remains foundation-only; real voice and request serving are
planned B integration work (VOX-1–4/SYSX-1), followed by planner/gateway work in C.
No requirement IDs move phases. The role's Phase A gate requires the mock and
compiled types, not a finished desktop UI or real voice service. Native vault
authorization and Windows installation still need manual deployment smoke tests.
Phase B can now begin with the offline voice loop and its real transport.

## Contract and test workflow

For each user-visible feature, add the scenario in `tests/e2e/scenarios` first.
Tell the frontend developer before a contract change and follow
API_CONTRACT.md's approval/versioning requirements. Generate schema from the
Pydantic source; never hand-edit generated files. This architecture map does
not authorize a contract change.

Put service unit tests beside that service and cross-component scenarios in
`tests/e2e/agent`. Use public or fictional library documents, consenting
fixture speakers and fake mail/network/model clients. Real model evaluations
remain separate from unit tests and require an explicit spending cap.

Add modules only when their phase and requirement call for them. Keep the UI
in apps/desktop under frontend ownership. The Local model profile remains
later work: implement configuration and routing boundaries without adding an
on-device Gemma runtime to the MVP.
