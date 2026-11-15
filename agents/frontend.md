# Role: frontend engineer

You own `apps/desktop` (Tauri shell and React UI), frontend unit/Playwright tests
and desktop installer work with the backend engineer. The user wants you to start
now while backend work continues. Build against the mock; do not wait for models,
a provider account or the full real service.

Read AGENTS.md and the ordered core documents, then:

1. `docs/FRONTEND_DESIGN.md`: recommended design, behaviour, safety and event mapping.
2. `apps/desktop/design/presentation.html` or its PDF: visual proposal, not a live app.
3. `docs/FRONTEND_HANDOFF.md`: actual setup, authentication, generated types and gaps.
4. `docs/BACKEND_HANDOFF.md`: backend implementation versus outstanding acceptance.

## Current status

- [x] Design proposal, offline HTML/PDF presentation and Signal A SVG logo assets.
- [x] Shared design tokens and implementation brief linked from the repo entrypoints.
- [x] Generated public v1 contract types and authenticated mock are available.
- [ ] Production React/Vite frontend and Tauri scaffold.
- [ ] F0–F6 implementation and real Windows/staff acceptance below.

Do not mistake checked design/contract artifacts for implemented UI. Check the
current checkout before relying on uncommitted backend work or newly added fixtures.
The old inspiration blueprint is reference material; the new design brief is the
UI recommendation. The PRD and contract remain authoritative over any mockup.

## Stack and ownership

Use the agreed React + TypeScript + Vite direction, Tauri shell, CSS modules or
plain scoped CSS using the shared tokens, Vitest/React Testing Library, Playwright,
eslint, prettier and pnpm. Follow repository pins for Node/pnpm and locked installs.
No runtime font/CDN dependency. Native Windows/system fonts are the default.

Keep generated `src/contract/` files and import `WireAgentEvent`, `WireUIEvent`,
`CONTRACT_VERSION`; never create a second handwritten wire schema. The UI sends
requests only to the local agent. It does not access audio, files, provider APIs,
credential stores or tools directly. Do not add v1 events or REST capabilities
without backend agreement and a scenario. No `audio.level` stream exists today.

Suggested frontend structure (create during F0, not empty scaffolding now):

```
src/
  contract/             # existing backend-generated files; do not hand-edit
  app/                  # navigation, shell, composition
  transport/            # authenticated client, validation, connection lifecycle
  state/                # event reducer; separate pending approval/confirmation
  components/           # reusable controls, status, captions, dialogs
  features/             # assistant, policies, outbox, activity, settings/profiles
  styles/               # imported design tokens, layout, accessibility themes
  strings/              # UI copy kept separate from component logic
src-tauri/              # lifecycle/window/sidecar packaging in F6
```

## F0 — scaffold and mock connection

Requirements: DEP-1/DEP-4 foundations; SYSX-1 transport support.

- [ ] Scaffold Vite/React/TypeScript without replacing `src/contract/`.
- [ ] Add Tauri project and pnpm scripts: dev, build, gen:types, lint, typecheck,
  test, e2e and tauri. Use the existing isolated contract generator for gen:types.
- [ ] Apply `design/tokens.css`, the JSON type/layout tokens and Signal A assets.
- [ ] Build the idle workspace: forest sidebar, light work area, header and composer.
- [ ] Authenticate health/WS with the mock's supplied per-session token; never log URLs/tokens.
- [ ] Runtime-validate incoming messages and handle malformed/unsupported messages visibly.
- [ ] Implement a reducer for status, partial/final transcript, captions and results.
- [ ] Handle transport errors and normal fixture completion; avoid reconnect replay loops.
- [ ] Add unit tests and one Playwright `policy_question` replay through approval/source opening.
- [ ] Run lint/types/tests, generated contract checks and the mock scenario in CI.

First reviewable delivery: idle shell + authenticated mock + one working event
replay. Avoid building every future screen in the first PR.

## F1 — core voice/task screens

Requirements: VOX-1–4, SYSX-1, SYSX-3, DEP-3.

- [ ] Persistent status, connectivity and active Hosted/Local profile shown separately.
- [ ] Partial transcript replaced until final; optional speaker handled without guessed identity.
- [ ] Every reply rendered as captions, including `spoken: false`.
- [ ] PTT pointer/hotkey start/stop paired on release, capture loss, blur and unmount.
- [ ] Distinct Stop speech and Cancel task controls, using known task IDs only.
- [ ] Floating widget with state and return-to-main behaviour.
- [ ] Deterministic listening animation; reduced motion gives static status, no fake amplitude.
- [ ] Microphone availability shown honestly; global mute awaits a backend-owned capability.
- [ ] Replay `voice_echo`, local-policy and fallback scenarios; verify 900 × 600 layout.

## F2 — safety first

Requirements: ID-2/ID-5, MAIL-1, REPLY-3 and the PRD cloud-upload rule.

- [ ] Separate CloudApprovalDialog and ActionConfirmDialog with separately correlated IDs.
- [ ] Complete exact payload preview as escaped/plain text, no silent clipping or rewriting.
- [ ] Read-back details: dry-run text, all recipients, subject and attachments as supplied.
- [ ] Explicit click/key activation only; spoken yes/Enter in composer cannot send.
- [ ] Safe initial focus, focus trap/restore, keyboard access and no countdown auto-approval.
- [ ] Expire stale controls on cancellation/replacement/disconnect; no approval replay.
- [ ] Speaker confirmation asks one supplied question; never guesses a profile.
- [ ] Errors/fallback/decline retain useful local results and show plain-language recovery.
- [ ] Unit and Playwright checks prove decline, double-click, disconnect and voice-only refusal.

## F3 — work screens

Requirements: POL-1–5, DOC-1–2, RPT-1–2, SUM-1–3, MAIL-1–3, REPLY-1–3, SYSX-2.

- [ ] Policy answer/passage cards with title, literal excerpt and unknown date/page handling.
- [ ] Send source.open with exact latest returned file_path/page; disable stale sources.
- [ ] Library setup/status empty/error/loading screens, connected once real APIs exist.
- [ ] Document-result card; arbitrary Word opening needs its own supported backend route.
- [ ] Summary/report/memo previews only from supported backend results, no invented fields.
- [ ] Outbox read-only list for all five received states, recipients, subject and attempts.
- [ ] Add edit/retry/discard/cancel only after backend APIs/scenarios exist; no direct sends.
- [ ] Activity entries by ID, undo only when supplied and supported; no fabricated success/history.
- [ ] Replay relevant committed mock scenarios, then connect supported real-agent paths.

## F4 — profiles and settings

Requirements: ID-1–5, DEP-3, VOX-4, POL-1.

- [ ] Agent-owned microphone/folders/profile settings; signature, sender and tone per user.
- [ ] Enrollment privacy/consent, guided speech, progress and explicit error states.
- [ ] Confirmed deletion and honest removal results, never a frontend-only reset.
- [ ] Hosted/Local profile UI reflects actual availability; Local model remains P1.
- [ ] Real API integration and profile separation verified with backend; no fake completion.

## F5 — accessibility throughout, then explicit acceptance

Requirements: PRD section 6 accessibility and all applicable functional requirements.

- [ ] 16 px reading text, 14 px labels, 44 px targets and visible keyboard focus.
- [ ] High contrast, 125%/150% text, system reduced motion and screen-reader labels.
- [ ] Polite state/final-caption announcements; avoid announcing every partial syllable.
- [ ] All dialogs and source drawers keyboard-accessible; controls reachable at 900 × 600.
- [ ] Verify 200% Windows scaling, long content, keyboard-only operation and contrast.
- [ ] Automated accessibility checks plus real staff-PC usability; no animation-only meaning.

## F6 — shell and release

Requirements: DEP-1–2, VOX-4, SYSX-1; shared with backend packaging phase I.

- [ ] Tray/widget lifecycle, single instance and reviewed hotkeys/startup behaviour.
- [ ] Sidecar start/stop/recovery and protected per-session token handoff.
- [ ] Actual app/tray icon exports, licences and accessibility/native window verification.
- [ ] Signed installer/update pipeline with backend; clean Windows/network-off startup.
- [ ] Real-agent smoke scenarios, measured startup/performance and non-technical staff trial.

## Completion and collaboration

For each slice: scenario before new visible protocol behaviour, small normal PR,
requirement IDs, unit/Playwright/lint/type checks and updated decisions. No drafts.
Do not wait for the backend to finish independent UI work. Document missing APIs
and keep their controls unavailable until the interface and behaviour are agreed.

Preserve concurrent backend changes; work on your own short-lived frontend branch
after receiving this handoff. A phase is complete
only when its stated mock checks pass, real supported paths are exercised and the
required Windows/staff acceptance is recorded. Green mock replay alone is not a
released feature.
