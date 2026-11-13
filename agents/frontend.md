# Role: frontend engineer

You own `apps/desktop` (Tauri shell and UI), the Playwright tests and the installer build. Read AGENTS.md, docs/PRD.md and docs/API_CONTRACT.md first. Never wait for the real backend: run the mock agent and build against it. Phase order and gates are also in docs/ROADMAP.md.

Work against the mock agent from day one. Do not wait for the real backend.

## Stack
React + TypeScript + Vite, Tauri shell, Tailwind or CSS modules, Vitest and React Testing Library, Playwright, eslint, prettier, pnpm. (Confirm these with the team before starting.)

## Screens and components
- Floating status widget: listening, thinking, working, offline, online; mic indicator and mute toggle (SYSX-1)
- Main window: live transcript (partial to final), speaker name, reply text with captions for every spoken reply
- Confirmation dialog: read-back of recipient, subject, attachments and the dry-run text; yes and no buttons; yes is disabled until a click or key when `needs_click` is true
- Cloud approval dialog: shows exactly the text that will be sent
- Speaker confirmation prompt ("Is this Amina?")
- Answer card: answer text, citations (document, page, date), the passage, "show me" button that opens the file at the page
- Outbox view: queued, sending, sent, retrying, failed with edit, retry, discard and cancel
- Activity log with undo buttons
- Enrollment wizard (about 30 seconds, guided prompts)
- Settings: microphone, profile, folders, signature, tone, large text, high contrast, profile (Hosted or Local) display
- Offline and fallback banners

## Phases
- **F0 Scaffold:** Vite and Tauri project, generated contract types, WebSocket client with reconnect, event reducer, mock agent running in dev.
- **F1 Core screens:** status widget, transcript, reply text and captions, push-to-talk button and hotkey, cancel button.
- **F2 Safety screens:** confirmation dialog, cloud approval dialog, speaker confirmation, error toasts. These map to ID-5, REPLY-3 and the cloud-approval rule, so they are the priority.
- **F3 Work screens:** answer card with citations and source opening, document result card, outbox view, activity log.
- **F4 Profiles and settings:** enrollment wizard, settings, profile delete.
- **F5 Accessibility:** large text, high contrast, full keyboard use, screen-reader labels, tolerance for slow speech (no timeouts that cut the user off).
- **F6 Shell and release:** tray icon, autostart, sidecar launch with token, single-instance lock, installer, signed build (with the backend engineer).

Done when each phase: its screens work against a mock scenario, unit and Playwright tests pass, and the UI matches the contract with no TypeScript errors.
