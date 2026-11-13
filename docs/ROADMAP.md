# Roadmap

No dates. Phases run in order, and a gate must pass before the next phase starts. Backend and frontend work in parallel tracks, joined through the contract (docs/API_CONTRACT.md) and the mock agent.

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

- Do not start a phase until the previous gate passes.
- Do not build anything not in docs/PRD.md section 3.
- A scenario file exists for every user-visible feature before either side builds it.
- Move a requirement between phases only through a line in docs/DECISIONS.md.

## Risks to watch

See docs/PRD.md section 9. The three that hurt most if ignored: slow or low-RAM PCs, poor recognition of Nigerian accents and names, and wrong or uncited policy answers.
