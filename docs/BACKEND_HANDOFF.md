# ARIA backend and AI engineering handoff

Updated: 14 November 2026. Owner: backend and AI engineer.

This is the continuation checklist for the backend. Start here after reading
AGENTS.md, PRD.md, TECH_SPEC.md and your role guide. The PRD defines requirements;
this document records implementation progress and the work needed to deliver them.
A checked item means the stated implementation exists and has the stated evidence.
It does **not** mean the entire product or phase has passed staff acceptance.

## 1. What we are trying to deliver

ARIA is a voice assistant on each staff member's Windows PC. Staff should be able
to ask for policy passages, open approved applications and sources, manage their
calendar, prepare Word documents, summarise information and prepare email replies.
The assistant must ask before actions that write, send, delete or overwrite.

Most processing stays on the PC: microphone, speech recognition, speech output,
search, files, calendar, profiles, encrypted history and the offline email outbox.
A small cloud gateway holds the model API key and receives only approved request
text and selected excerpts. Audio, credentials and the whole library never go there.
The model proposes a plan; registered, validated tools carry out approved actions.

The intended path is:

`request -> local keyword match or approved planning -> validation -> required
confirmations -> registered tools -> results/activity -> captions/speech`

The present implementation has separate foundation, voice-echo and local-text
entrypoints. They are **not yet one complete production voice assistant**.

## 2. User instructions that the next agent must preserve

- The role in this thread is already **backend and AI engineer**. Do not repeatedly
  ask the user to select it. Follow AGENTS.md for a genuinely new session/unknown role.
- Finish independent backend work before asking for models, provider accounts or
  API keys. Voice assets and live Gemma setup are explicitly deferred, not cancelled.
- Public policy test documents must be **Nigerian**. Use verified Nigerian issuing
  bodies and preserve source links, original bytes, checksums and honest metadata.
- Improve retrieval against the fixed 30 questions. The user asked for the best
  possible result; do not weaken labels or call a small benchmark universal perfection.
- Use simple human commit messages. Open normal, ready-for-review pull requests,
  **never drafts**. Push completed work and provide its PR link. Do not auto-merge.
- Keep frontend work in `apps/desktop` with the frontend engineer. Preserve the
  public contract unless the documented frontend approval process is followed.
- A pre-existing user edit adds a blank line in `agents/backend-ai.md`. Preserve it
  and leave it unstaged; do not include it in your commits or discard it.

Sequencing exceptions are recorded in DECISIONS.md, especially decisions 26, 30,
35 and later entries. They permit independent implementation while acceptance
checks remain open. They do not waive privacy, confirmation or release requirements.

## 3. Where the backend is located

| Location | Purpose and current status |
|---|---|
| `services/agent/src/agent/` | Python service running on the staff PC |
| `services/gateway/src/gateway/` | FastAPI gateway; real provider is still a placeholder |
| `apps/desktop/` | Frontend/Tauri ownership; generated contract artifacts exist |
| `docs/` | Requirements, specifications, implementation guides, decisions and this handoff |
| `library/policies/` | Three deliberately fictional demo policies |
| `library/public_policies/` | Current work: eight original Nigerian NITDA PDFs and provenance |
| `tests/kb_questions/` | Current work: fixed 30-question labels and retrieval reports |
| `tests/e2e/scenarios/` | Public event sequences shared by mock/backend/frontend |
| `services/agent/tests/unit/` | Network-blocked agent unit tests |
| `services/gateway/tests/unit/` | Network-blocked gateway unit tests |
| `scripts/` | Contract generation, verification, worker smoke and benchmarks |

Important module boundaries:

- `config.py`, `logging_config.py`: settings and content-free diagnostics.
- `store/`, `security/keys.py`: SQLCipher, native vault keys, migrations and retention.
- `interfaces/`, `fakes/`, `bootstrap.py`: adapter contracts, explicit test doubles and lifecycle.
- `audio/`, `voice/`: local speech pipeline and authenticated echo service.
- `contracts/`, `mock/`: UI schema and authenticated scenario replay.
- `planner/`: local keywords, strict plan validation and safe step references.
- `llm/`: gateway payload approval, client, connectivity and retry/fallback.
- `router/`: session ownership, cancellation, executor and confirmations.
- `tools/`: registry, killable process runner, Windows app launcher and ICS reader.
- `kb/`: document reading, encrypted indexing, retrieval, citations and source opening;
  current work also adds evaluation and improved lexical retrieval.

Do not create empty directories and call a feature implemented. File existence,
fake adapters and scenario replay are not evidence that a real feature works.

## 4. Implemented work and evidence

### A. Foundations — backend foundation gate passed

Requirements: DEP-1 and DEP-4 foundations; privacy/storage requirements.

- [x] Python 3.11 uv workspace, lockfile, ruff, mypy, pytest and pre-commit checks.
- [x] Explicit TOML/environment settings with validation and protected secret handling.
- [x] Structured metadata-only logging; no source text or credentials in diagnostics.
- [x] SQLCipher-only encrypted storage with native Windows/macOS vault key providers.
- [x] Ordered, checksummed, transactional migrations; no plaintext or replacement-key fallback.
- [x] Transcript/activity retention of 30/90 days and recurring foundation cleanup.
- [x] Adapter interfaces and deterministic fakes; explicit injection only.
- [x] Startup/shutdown/partial-failure cleanup and offline foundation checks.
- [x] Pydantic event/plan schemas, generated JSON Schema/TypeScript and freshness checks.
- [x] Authenticated localhost mock with correlated approvals and scenario replay.
- [x] Backend CI, platform tests and real localhost mock smoke verification.

Still needed: native vault permission/recovery and real Windows deployment checks.
The history repository exists; live sessions do not yet have durable profile-bound history.

### B. Offline voice pipeline — code exists, acceptance deferred

Requirements: VOX-1 to VOX-4, SYSX-1.

- [x] Bounded in-memory audio frames, wake ring buffer and push-to-talk path.
- [x] VAD/endpointing and local adapter wrappers for Silero, openWakeWord,
  faster-whisper and Piper.
- [x] Partial/final captions, spoken-echo orchestration, stop/barge-in and cleanup.
- [x] Authenticated voice transport and stub-engine tests; Windows native import CI.
- [x] Voice benchmark/word-error-rate utilities.
- [ ] Supply and checksum real local Whisper, Piper and Silero assets.
- [ ] Train/export a custom HeyAria model; evaluate it with consenting speakers.
- [ ] Verify push-to-talk and spoken echo on Windows with internet disabled.
- [ ] Collect 100–200 consented Nigerian-English sentences; measure WER and latency.
- [ ] Measure wake false accepts and speech startup/stop performance.
- [ ] Connect voice requests to real task routing, with identity and approvals.
- [ ] Verify frontend mic/hotkey/Stop/status/captions against the real voice service.

Wake-word activation must remain disabled without a valid model. Never download
assets at runtime, store raw audio by default or substitute fake engines after failure.
See VOICE_LOOP.md and ROADMAP.md's deferred list.

### C. Planner, gateway and execution — internal paths implemented

Requirements: DEP-3, DEP-4, SYS-1, CAL-1, SYSX-3.

- [x] Strict schema ingestion, registered tool authority and clarification checks.
- [x] Tool input/output/risk/network/timeout/dry-run declarations.
- [x] Bounded local keywords for configured apps, today's calendar, cancel and policy search.
- [x] Agent HTTPS gateway adapter and deterministic fake adapter.
- [x] Exact-payload cloud preview, single-use approval and policy/connectivity rechecks.
- [x] At most two gateway attempts within the shared eight-second budget; visible fallback.
- [x] Local session/executor, per-action click/key confirmation and activity events.
- [x] Killable worker subprocesses, strict result validation, timeout/cancellation cleanup.
- [x] Allow-listed Windows executable launching and read-only local ICS listing.
- [x] Typed `$stepN.field` bindings to earlier results, with graph/runtime validation.
- [x] Gateway-plan handoff to the executor, keeping upload approval separate from actions.
- [x] No late dispatch after cancellation/replacement; replayed approvals cannot act.
- [x] Actual in-memory gateway API tested with a fake provider; real workers smoke-tested.
- [ ] Implement the selected live provider in `gateway/llm.py`; `ProviderLLM` raises
  `NotImplementedError` today. Do not report a live Gemma connection as finished.
- [ ] Build the hosted application assembly/request builder and wire approved
  planning into the final desktop/voice flow. `agent.local` deliberately disables cloud use.
- [ ] Complete grounded planning checks for names, dates, amounts and recipients;
  never treat structural plan validation as proof of factual grounding.
- [ ] Resolve purpose-based app requests to known configured apps, with clarification for ambiguity.
- [ ] Verify actual Windows "Open Excel" and calendar performance, including the under-1s gate.
- [ ] Verify approved live gateway success and gateway-down fallback on staff hardware.

Gateway production work still required:

- [ ] Replace in-memory limits/counters with persistent, concurrency-safe enforcement.
- [ ] Implement a real daily budget window/reset and approved per-user identity mapping.
- [ ] Reserve/enforce spend safely before concurrent provider requests; reconcile actual usage.
- [ ] Replace starter price assumptions with verified provider billing configuration.
- [ ] Provision/revoke/rotate installation tokens and test cross-install isolation.
- [ ] Enforce request/body/excerpt bounds, timeouts and content-free usage audit records.
- [ ] Deploy authenticated HTTPS, health/operational monitoring and recovery procedures.

Do not replace working interfaces with a chosen provider's SDK throughout the app.
See PLAN_VALIDATION.md, KEYWORD_PLANNER.md, GATEWAY_INTEGRATION.md,
LOCAL_EXECUTION.md, STEP_RESULTS.md and CLOUD_EXECUTION.md.

### D. Policy library — D1/D2 implemented; current retrieval work below

Requirements: POL-1 to POL-5.

- [x] Read local UTF-8 text, DOCX and text-bearing PDF documents.
- [x] Preserve explicit manifest titles/numbers/dates, PDF pages and text/Word sections.
- [x] Encrypted FTS5 cache, per-document atomic refresh and removal of stale passages.
- [x] Refresh before search and explicit five-second CLI watch maintenance.
- [x] Offline citations, closest-match/no-match messages and session activity.
- [x] Source opening restricted to the latest published session citations.
- [x] Recheck source bytes, metadata, index/page and configured path before viewer launch.
- [x] Configured Windows viewers, fixed Sumatra PDF page arguments and honest fallback.
- [x] Source-opening scenarios, native-launch stubs and actual-worker snapshot checks.
- [ ] Verify installed viewers and page navigation on real Windows staff PCs.
- [x] Nigerian corpus/evaluation and improved lexical search verified locally; see current-work evidence below.
- [ ] Add local embeddings and sqlite-vec hybrid retrieval when model work resumes.
- [ ] Decide final model-token chunking and passage count using evaluation results.
- [ ] Implement grounded answer generation using approved selected passages only.
- [ ] Validate every claim/citation, handle conflicting dates and honest unsupported answers.
- [ ] Complete the full 30-question answer/citation/not-found quality gate at 90% or above.
- [ ] Add frontend library selection/index-status controls and verify real search/source UI.
- [ ] Expand/review real Nigerian HR/travel/office-policy coverage when staff-approved sources are available; current public fixtures are IT/governance focused.
- [ ] Test document changes, removed sources, sleep/wake and large-library performance on staff PCs.

Current windows use up to 400 whitespace-separated words with 50-word overlap,
not a promise about model token counts. PDF extraction/table limitations and scanned
PDF rejection are documented. Runtime OCR remains outside the MVP. Unknown dates
and DOCX/TXT page numbers must remain unknown.

See OFFLINE_POLICY_SEARCH.md and OPEN_POLICY_SOURCES.md. A keyword score is not
an AI-answer quality score and cannot pass the full Phase D gate by itself.

### E. Word documents, reports and summaries — not implemented

Requirements: DOC-1, DOC-2, RPT-1, RPT-2, SUM-1 to SUM-3.

- [ ] Implement document tools behind the existing Tool/LLMAdapter interfaces.
- [ ] Create and review Word memo templates with letterhead and consistent styles.
- [ ] Extract a brief's known fields and ask one missing-detail question at a time.
- [ ] Generate a memo draft without inventing names, dates or amounts.
- [ ] Confirm writes/overwrites and save only in the configured user's folder.
- [ ] Use topic/date filenames from known facts; open the resulting Word document.
- [ ] Propose report outlines, obtain approval, write sections and redo one section safely.
- [ ] Implement one-line, five-bullet and one-page document/email summaries.
- [ ] Add page/heading references and source checks for numbers, dates and proper nouns.
- [ ] Flag unsupported facts before presenting a summary as faithful.
- [ ] Add fictional scenarios, unit tests and real Word acceptance checks.
- [ ] Pass the reviewed-summary gate: at least 9 of 10 contain no invented facts.

### F. Email, outbox, calendar changes, files and system tools — mostly pending

Requirements: MAIL-1 to MAIL-3, REPLY-1 to REPLY-3, CAL-2, SYS-2, SYS-3, SYSX-2.

- [x] Reusable execution/confirmation framework, app allow-list, read-only ICS and policy-only source opening.
- [ ] Add Microsoft Graph and Gmail adapters with OAuth, narrow scopes and native-vault tokens.
- [ ] Find a thread from its description; confirm sender/subject and handle ambiguity.
- [ ] Draft replies with the correct user's signature/tone and show/read them back.
- [ ] Resolve attachments by description and ask when multiple files match.
- [ ] Call out reply-all/external recipients and require click/key confirmation before send.
- [ ] Persist an outbox row before any send, with a unique idempotency key.
- [ ] Implement queued/sending/sent/retrying/failed transitions and a separate worker.
- [ ] Add real endpoint connectivity checks, bounded retry/backoff and cancel/discard handling.
- [ ] Prove crash/reconnect retries send exactly once; never silently repeat an uncertain send.
- [ ] Add local calendar create/move/cancel, conflict detection and required confirmations.
- [ ] Add general file search by filename, recency and indexed content; policy opening is not this feature.
- [ ] Implement only approved system actions: volume, focus and print.
- [ ] Persist plain-language activity under a verified profile and add undo where possible.
- [ ] Pass the offline-confirmed-reply/reconnect/exactly-once acceptance gate.

### G. Speaker identity and profiles — not implemented

Requirements: ID-1 to ID-5.

- [ ] Obtain explicit enrollment consent and provide the privacy/deletion flow.
- [ ] Implement the speaker adapter and approximately 30-second enrollment.
- [ ] Encrypt/store embeddings under the correct profile.
- [ ] Identify speakers with measured thresholds; ask on low confidence instead of guessing.
- [ ] Bind folders, signature, sender, tone, history and queued items to verified profiles.
- [ ] Implement profile APIs and deletion of embeddings/history/queued items/related data.
- [ ] Prove profile separation for two or three consenting users.
- [ ] Measure held-out accuracy; voice alone must never authorize send/delete actions.

Foundation profile tables and fake speaker IDs are not completed speaker recognition.

### H. Evaluation, security and performance — acceptance work pending

Requirements: PRD sections 4, 6 and 7; safety requirements across all features.

- [ ] Preserve the fixed Nigerian retrieval set and independent regression cases.
- [ ] Evaluate real model answers/drafts/replies on the agreed tasks when setup resumes.
- [ ] Verify actual supported model IDs/capabilities; compare candidates on quality, speed and cost.
- [ ] Record provider data-use/region/retention terms and a spending cap before paid/live tests.
- [ ] Test at least ten malicious documents/emails for instruction injection.
- [ ] Prove source content cannot add tools, change recipients or bypass confirmation.
- [ ] Test request/excerpt limits, malformed inputs, token isolation and source/path boundaries.
- [ ] Test Windows sleep/wake, network drops, interrupted tasks and crash recovery.
- [ ] Measure all PRD latency/CPU/memory targets on a real supported 8 GB staff PC.
- [ ] Complete the Nigerian data-protection/privacy review before a real pilot.

Targets to measure, not assume from CI: keyword commands under 1s; transcript
within 1.5s; TTS start within 500ms; short cloud first words under 3s; cited answer
under 6s; two-page summary under 10s; memo first text under 5s; ready within 90s;
idle CPU under 5%. Record WER and wake false accepts against TESTING.md's targets.

### I. Packaging, release and operations — not implemented

Requirements: DEP-1, DEP-2; shared work with frontend.

- [ ] Package the Python agent and worker entrypoint as a Windows sidecar.
- [ ] Integrate Tauri process startup, session-token delivery and lifecycle/recovery.
- [ ] Bundle reviewed/checksummed speech, speaker, embedding and wake assets with licences.
- [ ] Load/warm models once; no downloads at runtime.
- [ ] Build/sign the Windows installer and update artifacts.
- [ ] Implement and verify release/deploy workflows; existing YAML files are not proof of deployment.
- [ ] Install/start on a clean Windows PC offline, ready within 90 seconds.
- [ ] Complete all 15 product e2e scenarios for three runs, plus real staff-PC smoke tests.
- [ ] Have a non-technical staff member try the real features; record results and remaining defects.
- [ ] Document operational health, diagnostics without personal content, key/backup recovery and rollback.

P1 items such as OCR, phone clients, a local Gemma runtime, extra users and an
admin console must not creep into MVP work without explicit scope approval.

## 5. Latest implemented slice: Nigerian corpus, evaluation and better keyword decisions

Working branch: `backend/policy-evaluation`.
Prior feature PRs: #18 offline search and #19 source opening. Check their live merge
state before branching/rebasing; do not merge on the user's behalf.

The user first requested the corpus/evaluator, then explicitly required Nigerian
public documents and asked to improve the original 11/30 keyword decision score.
They also requested this handoff so another agent can continue without losing context.

Implemented and locally verified in this change:

- [x] Eight original NITDA PDFs with official Nigerian URLs, byte counts, checksums and provenance.
- [x] Three existing fictional policies kept separate from real sources.
- [x] Root/collection manifests with honest unknown dates/numbers; no U.S. documents retained.
- [x] Thirty fixed questions: 20 source-supported and 10 unsupported, with checked evidence/page labels.
- [x] Offline evaluator using only temporary encrypted fake-key storage, never live services/vaults.
- [x] Original baseline report: 18/20 support hits, 10/10 correct no-match signals,
  227/227 intact citations, but only **11/30 full keyword decision cases**.
- [x] Initial improved run: **30/30 keyword cases**, 20/20 support hits, 10/10
  no-match cases and 157/157 intact citations on the same fixed set.
- [x] Eighteen additional regression checks: ten paraphrases, six unsupported questions,
  migration preservation and explicit ranking modes. These are regression cases, not a blind external test.
- [x] Before/after reports retained with identical corpus and question hashes.
- [x] Migration-3 preservation/stemming/heading checks and the full local suite:
  **543 agent + 12 gateway = 555 Python tests**, lint/format, mypy and contract checks.
- [x] Real-worker smoke passes; no real model/app/vault is used by evaluation tests.
- [x] Documentation, onboarding links and CI report-artifact wiring implemented.
- [ ] User review/merge and the real staff/model/voice acceptance tasks listed above.

Hosted CI is live state: inspect the newest check run on this branch's PR before
claiming it is green. Find the PR through the repository's pull-request list or
`gh pr view --json url,state,statusCheckRollup` when available. Recheck merge state
before starting another branch; do not duplicate or discard this work.

The improved search adds English stemming, indexed headings, bounded reusable
lexical families, question-word handling, relevance-first ranking and weighted
keyword coverage. Newest-first listing is explicit. No question IDs/expected
answers are used by runtime retrieval; golden labels belong only to evaluation.
The full Phase D gate stays open even if the fixed keyword set reaches 30/30.

Important current files:

| File | Purpose |
|---|---|
| `library/public_policies/provenance.json` | Source URLs, SHA-256 hashes, retrieval dates and date caveats |
| `tests/kb_questions/golden_set.json` | Fixed 30 questions and source evidence; do not rewrite to inflate scores |
| `tests/kb_questions/reports/keyword_baseline.json` | Original, honestly failing 11/30 decision baseline |
| `scripts/bench_policy.py` | Offline scoring CLI; optional explicit keyword threshold; refuses output overwrites |
| `services/agent/src/agent/kb/evaluation.py` | Input verification, evidence checks and scoring |
| `services/agent/src/agent/kb/retrieval.py` | New bounded retrieval strategy behind PolicyRetriever |
| `services/agent/src/agent/store/migrations/v003_retrieval.py` | Rebuilds FTS with stemming/headings while preserving rows |
| `services/agent/tests/unit/test_policy_evaluation.py` | Scorer/data-integrity tests |

Some documents state only a year/month. Do not infer issue dates from upload URLs.
The 2026 cloud guideline separately states approval 4 August 2026 and effective
1 January 2027; record those labels rather than claiming it is already effective.
The source snapshots are retrieval fixtures, not a declaration that every included
regulation is current or applies to the user's organisation.

## 6. Exact continuation commands

From the repository root, with Python 3.11, uv 0.13.7 and Node 24 installed:

```sh
git status --short
git branch --show-current
uv sync --locked --all-packages --all-extras
uv run --locked --all-packages --all-extras python scripts/check_backend.py
node scripts/contract/check.mjs
uv run --locked --all-packages --all-extras python scripts/smoke_execution.py
uv run --locked --all-packages --all-extras python scripts/smoke_mock.py
uv run --locked --all-packages --all-extras python scripts/bench_policy.py
```

Install the pinned contract tools once with
`corepack pnpm --dir scripts/contract install --frozen-lockfile`.
If uv is only in the local virtual environment, `.venv/bin/uv` is available on
this development machine. Use the Windows `.venv/Scripts` equivalent where needed.
Do not replace the lockfile or access real credentials just to make tests pass.

Useful smoke/demo commands:

```sh
uv run --locked --all-packages --all-extras python -m agent --fake --check
uv run --locked --all-packages --all-extras python -m agent.kb --demo --query "annual leave"
uv run --locked --all-packages --all-extras python -m agent.local --tools config/local-tools.example.toml --command "calendar today"
uv run --locked --all-packages --all-extras python -m agent.mock --scenario open_policy_source
```

The mock never proves real viewer/mail/model behavior. The KB demo is fictional
and temporary. The real local service needs explicit file/app/viewer configuration.
Never print token-bearing local session URLs into public issues or commits.

Before every commit: lint, format, mypy, unit tests and contract freshness must pass.
After a public schema/scenario change, regenerate the schema/types/examples using
the documented scripts. Do not hand-edit generated artifacts or applied migrations.
Use the PR template, reference requirement IDs and distinguish code/tests from
real acceptance. Preserve unrelated user edits and check hosted CI before claiming success.

## 7. How to choose the next task

1. Read the current-work section and DECISIONS.md, then inspect the actual branch/diff.
2. Inspect/finish review and the newest CI for this retrieval/evaluation/handoff slice before starting another feature.
3. Keep provider/model/voice setup deferred until the user resumes it. Explain remaining
   acceptance gates without repeatedly asking for keys or recordings.
4. Pick one unfinished backend requirement in the permitted phase. A move to E/F/G
   before the earlier acceptance gate requires an explicit user sequencing decision. Add its scenario first
   when behavior is visible to the UI; keep existing contract fields where possible.
5. Implement against interfaces, test offline/failure/cancel paths and record significant choices.
6. Commit with a simple message, push a normal PR, and update this checklist with evidence.

The backend succeeds when the required real staff workflows work safely and meet
the acceptance/performance/privacy gates. A large test count, a perfect fixed-set
retrieval score or a green mock replay alone does not establish that outcome.
