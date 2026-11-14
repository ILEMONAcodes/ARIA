# Roadmap

No dates. Phases run in order, and a gate must pass before the next phase starts unless the user explicitly changes the order and it is recorded in docs/DECISIONS.md. Backend and frontend work in parallel tracks, joined through the contract (docs/API_CONTRACT.md) and the mock agent.

## Phases

### Phase 1: Core loop
Goal: a spoken request gets a spoken answer on the staff PC, with the network off.
- Backend (agents/backend-ai.md phases A, B, C): foundations, voice loop, planner, gateway, router, keyword path.
- Frontend (agents/frontend.md phases F0, F1): scaffold, status widget, transcript, replies, push-to-talk.
- Requirements: VOX-1 to VOX-4, SYSX-1, DEP-1 to DEP-4, SYS-1, CAL-1, SYSX-3.
- **Loop gate:** works with the network off; latency and word error rate are logged; the mock agent and the real agent both drive the UI.

### Phase 2: Documents and policy search
Goal: memos, summaries and cited policy answers.
- Backend: phases D and E (knowledge base, documents, summaries, reports).
- Frontend: phase F3 (answer card, document result card), plus F2 safety screens.
- Requirements: DOC-1, DOC-2, RPT-1, RPT-2, SUM-1 to SUM-3, POL-1 to POL-5, SYS-2, SYS-3.
- **Gate:** 30-question set scores 90% or higher; a memo opens in Word with correct styles; 9 of 10 reviewed summaries have no invented facts.

### Phase 3: Mail queue
Goal: email replies with confirmation and an offline outbox.
- Backend: phase F (mail, calendar, outbox, activity log).
- Frontend: phase F3 (outbox view, activity log).
- Requirements: MAIL-1 to MAIL-3, REPLY-1 to REPLY-3, CAL-2, SYSX-2.
- **Gate:** a reply is drafted from a thread, confirmed, queued offline and sent exactly once when the network returns.

### Phase 4: Profiles
Goal: two or three people recognised, each with their own settings.
- Backend: phase G (speaker ID, profiles).
- Frontend: phase F4 (enrollment wizard, settings, profile delete).
- Requirements: ID-1 to ID-5.
- **MVP gate:** all 15 e2e scenarios pass three runs in a row in CI; smoke scenarios pass on a real 8 GB PC.

### Phase 5: Evaluation and hardening (runs alongside phases 2 to 4)
- Backend: phase H (model choice, prompt-injection corpus, latency benchmarks, provider data terms).
- Frontend: phase F5 (accessibility).
- **Gate:** eval results recorded in docs/DECISIONS.md; every speed target in PRD section 6 measured.

### Phase 6: Packaging and release
- Both: backend phase I and frontend F6 (sidecar, installer, signing, release workflow).
- **Gate:** a clean Windows PC installs the app and it starts with the network off, ready in under 90 seconds.

### After the MVP (P1)
Voice corrections and edits, PDF export, long documents, tone options, OCR, superseded circulars, calendar sync, the Local profile on Gemma 4 E4B or E2B, a phone browser client, up to 10 users, an admin console.

## Backend status

Backend status: Phase A's backend/contract gate passed CI. Phase B's offline
echo pipeline, optional local-model adapters and authenticated transport are
implemented; the actual Windows/network-off echo, model assets, Nigerian-English
WER, latency, wake-word evaluation and frontend integration remain pending.
See [VOICE_LOOP.md](VOICE_LOOP.md). The user has deferred the remaining voice
setup and evaluation (decision 26). Phase C has started with C1: strict plan
validation and tool registration/policy checks, using text inputs and fake tools
while voice work stays open. See [PLAN_VALIDATION.md](PLAN_VALIDATION.md).
C2 adds the internal [local keyword planner](KEYWORD_PLANNER.md) for configured
apps, today's calendar and cancellation, with clarification and no-match outcomes.
C3 adds the [gateway client and approval/retry/fallback flow](GATEWAY_INTEGRATION.md),
verified against the real gateway API with a fake provider. The user has also
deferred live provider selection/setup (decision 30). Live provider verification
and the full Phase C acceptance gate remain open. C4 adds the [local execution path](LOCAL_EXECUTION.md):
router/executor, per-step confirmations, killable workers, configured Windows app
launching, read-only ICS calendar, activity events and an authenticated text service.
The user's priority is to finish these non-model pieces before revisiting deferred
setup. Real staff-PC/frontend acceptance, durable profile history and dependent
result-reference workflows remain open; this does not mark the voice or live-provider gates passed.

## Deferred work: return before the MVP pilot

### Voice setup and evaluation

At the user's request, postpone these Phase B tasks rather than marking them
complete or moving them out of the MVP:

- [ ] Install the local Whisper, Piper and Silero speech models.
- [ ] Verify real push-to-talk and spoken echo on Windows with internet disabled.
- [ ] Train/export a custom HeyAria wake-word model using synthetic speech;
  test with consenting Nigerian-English speakers before enabling it by default.
- [ ] Collect 100–200 consented Nigerian-English sentences and measure WER.
- [ ] Measure transcript latency, TTS startup latency and wake false accepts.
- [ ] Verify the frontend hotkey, mic/Stop controls, captions and status against
  both the mock and real agent, then complete the non-technical user smoke test.

Resume after the independent Phase C implementation, or earlier at the user's
request. The Phase B/core-loop acceptance gate remains unpassed until these
checks succeed; they are still required before the MVP pilot/release.

### Live Gemma provider setup

The user has no provider yet and asked to track this work for later:

- [ ] Choose a Gemma API provider and verify its supported model IDs and capabilities.
- [ ] Create the provider account and obtain its API key. Configure it only in
  the gateway environment as `GATEWAY_PROVIDER_API_KEY`.
- [ ] Check data-use terms, region and current pricing; choose a spending cap.
- [ ] Implement/configure `ProviderLLM` for that provider and verify model/JSON-schema settings.
- [ ] Set up the authenticated HTTPS gateway URL and desktop installation token.
- [ ] Run explicitly approved live integration, timeout/fallback and model-quality
  tests using fictional/public data and an agreed budget before the MVP pilot.

Client integration and fake-provider tests can proceed while these stay open.

## Parallel work map

| Backend and AI | Frontend | Join point |
|---|---|---|
| Contracts and mock agent (first) | Scaffold, generated types | Mock agent scenarios |
| Voice loop, planner, router | Status widget, transcript, reply captions | `status`, `transcript.*`, `reply.text` |
| Gateway and approvals | Confirmation and cloud approval dialogs | `confirm.request`, `cloud.approval_request` |
| Knowledge base and documents | Answer card, document card | `result.answer`, `result.document` |
| Mail, outbox, activity log | Outbox view, activity log | `outbox.update`, `activity.entry` |
| Speaker ID and profiles | Enrollment wizard, settings | `/api/profiles/*`, `/api/settings` |
| Sidecar packaging | Tauri shell, installer | Release workflow |

## Build rules

- Do not start a phase until the previous gate passes, except for an explicit
  user-directed sequencing change recorded in docs/DECISIONS.md (currently
  decision 26 permits independent Phase C work while voice validation is deferred).
- Do not build anything not in docs/PRD.md section 3.
- A scenario file exists for every user-visible feature before either side builds it.
- Move a requirement between phases only through a line in docs/DECISIONS.md.

## Risks to watch

See docs/PRD.md section 9. The three that hurt most if ignored: slow or low-RAM PCs, poor recognition of Nigerian accents and names, and wrong or uncited policy answers.
