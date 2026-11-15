# ARIA desktop design and implementation brief

Updated: 14 November 2026. Audience: frontend engineer and any agent continuing UI work.

The user asked for a design presentation, a better ARIA logo and a practical handoff
so frontend work can begin independently while backend work continues. This is the
recommended design direction, **Forest & Paper**, ready for their review. It does
not change product scope, public events or backend completion claims.

## Start here

1. Open [the presentation](../apps/desktop/design/presentation.html) in a browser.
   Use Previous/Next, arrow keys or Page Up/Down. The PDF beside it is shareable.
2. Read this brief, [the frontend role](../agents/frontend.md),
   [the transport handoff](FRONTEND_HANDOFF.md) and [API_CONTRACT.md](API_CONTRACT.md).
3. Build F0 against the authenticated mock. No provider, API key, trained wake model
   or real microphone is required to begin frontend work.
4. Use [BACKEND_HANDOFF.md](BACKEND_HANDOFF.md) for backend availability. Design
   targets and replay fixtures do not imply production endpoints exist.

## 1. Design intent

ARIA should feel like a dependable office companion: welcoming at the start,
precise during a task and explicit before an action. Staff should always know
what it heard, what it is doing and what decision is theirs.

The supplied blueprint described a greeting, voice ring and green palette. Keep
those ideas, with a warm-white work area and a forest-green navigation column.
The supplied JPG contains NITDA/NCAIR/government logos; it is a **colour and
identity reference**, not an app layout. Other screenshots described by the old
blueprint were not present in this folder during this review.

Use the welcome screen for a greeting, one quiet listening motif and three request
starters. Use the same space for the actual task as soon as work begins. Avoid
analytics dashboards, invented task counts, large decorative orbs during reading,
subscription upsells, image generation and extra capabilities outside the PRD.

All names, messages and profile details in the presentation are fictional examples.
In the actual UI, use backend-provided identity or a neutral greeting. Do not assume
that the current Windows user is the identified speaker.

## 2. Identity and assets

Recommended logo: **Signal A**. Two ascending strokes form the initial; a short
pulse forms its crossbar. It connects voice with a distinct letter silhouette,
while the separate circular listening motif remains available in the interface.

| Asset in `apps/desktop/design/assets/` | Use |
|---|---|
| `aria-wordmark.svg` | Primary forest mark and outlined ARIA lettering |
| `aria-wordmark-white.svg` | Reversed wordmark on forest |
| `aria-mark.svg`, `aria-mark-white.svg` | Standalone symbol, normally 24 px or larger |
| `aria-mark-small.svg` | Simplified A, without pulse, for 16 px tray/favicon use |
| `aria-app-icon.svg` | Square app-icon concept; export required installer sizes during F6 |

Leave at least one quarter of the symbol width as clear space. Keep the SVG's
aspect ratio. Minimum full lockup width: 110 px. Do not glow, stretch or add an
emblem to the logo. The old `aria-logo-concept.svg` remains an earlier exploration,
not the selected implementation asset. The new marks are vector artwork, not an
alteration of the supplied official logos. Branding/trademark clearance and actual
installer icon exports are still release work.

Use ARIA as the product name and “Your office, by voice.” as the optional line.
Do not label it “official NITDA software” or imply government endorsement. The
reference informs proposed colours; these are not a verified official brand manual.
Keep the supplied official marks in the reference folder, outside the product UI.

## 3. Shared visual tokens

Canonical handoff: [design-tokens.json](../apps/desktop/design/design-tokens.json).
[tokens.css](../apps/desktop/design/tokens.css) provides matching colour variables
and core CSS primitives. Import it, then map the remaining JSON values into the
frontend's chosen styling system. Keep the two files aligned when changing tokens.

| Role | Value | Use |
|---|---|---|
| Action green | `#0B5A32` | Primary action, links, focus on light surfaces |
| Forest | `#103C2F` | Sidebar, icon ground, presentation identity |
| Paper | `#F5F6F2` | Main workspace |
| White | `#FFFFFF` | Cards and dialogs |
| Ink | `#172D24` | Main text |
| Secondary text | `#56685E` | Helper text and metadata |
| Sage | `#BCE5C7` | Quiet accent, not ordinary text on white |
| Control boundary | `#74867B` | Inputs and controls needing visible boundaries |
| Subtle divider | `#D5DFD7` | Nonessential card/section separators |
| Warning | `#805000` on `#FFF3DA` | Offline/approval warning, with words/icon |
| Error | `#A52828` on `#FCEDED` | Failure/destructive context, with words/icon |

Use Segoe UI/system sans for UI and Georgia/system serif for the welcome headline.
No network font imports. Use 16/24 px reading text, 14/20 px labels and metadata,
24/32 px screen titles and 36/44 px greeting. Large-text settings must enlarge real
content, not just the greeting. Presentation mockups are scaled compositions;
**do not copy their smaller screen-label sizes into production**.

Spacing: 4/8/12/16/24/32/48/64 px. Radius: 10 px controls, 16 px cards, 24 px major
panels. Reserve soft shadows for dialogs and elevated surfaces. Avoid transparency
behind text and perpetual GPU-heavy effects. Normal reading text must reach 4.5:1;
essential boundaries/icons and large text must reach 3:1. Verify the actual rendered
states, including focus, hover, disabled and high contrast; a palette is not an
accessibility certification.

## 4. Window and information architecture

Reference workspace: 1280 × 800; minimum window: 900 × 600. These are proposed UI
constraints, not new hardware requirements. Keep the native Windows titlebar and
window buttons initially; custom titlebars are optional F6 work, not an F0 blocker.

- Sidebar: 208 px at comfortable widths. Assistant, Policy library, Outbox, Activity;
  Settings and the current profile at the bottom. At narrower widths, collapse to
  a 72 px labelled/tooltip rail with accessible names.
- Header: 64 px. Current section, agent state, connectivity and Hosted/Local profile.
  Microphone availability must be visible even when the main window is closed.
- Workspace: 24–32 px padding. Content scrolls vertically; result text wraps.
- Context panel: 320 px for passage details or a task preview when space permits.
  Below 1200 px or at enlarged text, use a keyboard-accessible drawer instead.
- Composer: typed input, hold-to-talk and clear task cancellation. Make room for
  multiple lines. Do not obscure the last transcript or result at 600 px height.
- Floating widget: approximately 280 × 72 px, with state, mic availability and
  a way to reopen the main window. Review actual Windows DPI behaviour during F6.

No phone client, admin dashboard or new navigation section is implied. The Policy
library screen combines library setup/status and policy task results. Request
starters send/edit known request text; they do not invoke tools from the frontend.
Only show enabled actions when the connected transport supports the needed path.

## 5. Screen behaviour and requirement mapping

| Screen/component | Required behaviour | Requirement IDs |
|---|---|---|
| Idle assistant | Neutral/verified greeting, three request starters, composer, visible profile/network/mic state | SYSX-1, DEP-3, VOX-4 |
| Conversation/task | Partial/final transcript, current plan preview, reply captions, Stop speech and Cancel task | VOX-2–4, SYSX-1, SYSX-3 |
| Voice widget | Persistent readable state; open main window; no hidden listening | VOX-1, VOX-4, SYSX-1 |
| Policy result | Agent text, original passage, title, date/page if known, Show source | POL-2–5 |
| Library status/setup | Folder selection and indexing/errors through the agent; meaningful empty state | POL-1 |
| Cloud approval | Complete exact payload as plain text, decline/approve this request | DEP-4 and PRD section 4 cloud rule |
| Action confirmation | Exact dry run, recipients, subject, attachments, risk; explicit click/key response | ID-5, MAIL-1–2, REPLY-3, CAL-2 |
| Speaker check | One question using the supplied name; accept/reject without guessing | ID-2 |
| Document result | Returned title/path; only expose opening once a supported backend route exists | DOC-1–2, RPT-1–2 |
| Outbox | Five states; attempts/recipient/subject; honest offline and uncertain-send messaging | MAIL-3, REPLY-3 |
| Activity | Chronological agent entries; undo only when supplied and supported | SYSX-2 |
| Settings/profile | Microphone, folders, signature, tone, accessibility; enrollment consent and confirmed deletion | ID-1–5, DEP-3 |

### Voice, state and connectivity

Contract v1 has only `idle`, `listening`, `thinking`, `working` in `status.state`.
Connectivity (`online`) and execution profile (`hosted`/`local`) are separate axes.
Offline is not a replacement task state: a task can be working locally while offline.
An online event does not prove a model provider or Local model is configured.

Map idle to “Ready”, listening to “Listening”, thinking to “Thinking” and working
to “Working”. Show captions for every `reply.text`, regardless of `spoken`.
`spoken: true` does not indicate exact playback timing. Do not claim a live
speaking waveform or drive the ring from audio amplitude: **there is no
`audio.level` event**. A restrained 1.8-second CSS pulse during listening is a
status illustration only. Use a static ring/text under reduced motion. Never
capture audio through Web Audio, browser permissions or Tauri APIs to animate it.

A permission/mute toggle is a design target, but v1 has no general mic mute event
or configuration implementation. Do not mislabel `ptt.stop` as global mute. Until
a backend-owned capability exists, show availability/status honestly and record
the integration gap. Wake-word controls stay unavailable without a trained model.

### Policy and document results

Render `result.answer.text` as received; do not convert keyword passages into a
model-written answer. Offline copy must say passages were retrieved. A no-match
response may include closest documents: those are suggestions, not reliable answers.

Show dates with an unambiguous label and use “Date not provided”/“Page not provided”
for null fields. Preserve section headings in passage text. Never calculate a
physical page for TXT/DOCX. Never display a confidence percentage the backend
has not supplied. Avoid “current law” labels for fixture documents.

Send `source.open` with the exact returned `file_path` and `page`. No frontend
filesystem reads, path rewriting, browser `file://` opening or direct Tauri opener.
The real backend currently authorizes only the latest session's policy selections;
disable stale selections after replacement/disconnect. Opening a returned Word
result is not covered by this policy-only route: require backend agreement rather
than repurposing `source.open` for arbitrary paths. The source panel displays quoted
text, not a full PDF viewer or unapproved embedded document editor.

### Approvals and confirmation

Treat cloud approval and action confirmation as separate components and pending
records. Approval of an upload never approves its later actions.

- `cloud.approval_request`: show **the complete `payload_preview` unchanged**, as
  escaped/plain text in a scrollable area with wrapping. No ellipses in the real
  dialog. The deck abbreviates JSON only to illustrate layout. Reply with the exact
  `approval_id`, not a locally generated ID. Label actions “Keep on this PC” and
  “Allow this request”. Declining sends `decision: "no"`.
- `confirm.request`: render `dry_run_text` and all supplied `details`; default arrays
  may be empty. Show external recipients/reply-all information when provided.
  A plain email address alone is not evidence of organisational trust; do not invent
  an internal-domain classification. Reply with the exact `confirm_id`, decision
  and actual `via: "click" | "key"`.
- Use a modal dialog with a focus trap and a clear title. Initially focus the title
  or safe cancel action, not confirmation. Enter in the composer must never confirm
  a pending send. A key response means deliberate activation of the focused dialog
  control. No auto-submit after speech, countdown, timeout or reconnect.
- Consume an answer once locally, disable double-submit and await backend events.
  Invalidate stale confirmations on disconnect, cancellation and task replacement.
  Never replay an approval or an action on reconnect. Backend validation remains
  authoritative even if the frontend has guards.
- Speaker confirmation is a separate one-question prompt. Enrollment and deletion
  need their own backend APIs and privacy/confirmation flow; no fabricated success.

### Outbox and activity

Render queued/sending/sent/retrying/failed from `outbox.update`. Do not infer sent
from a transport response or repeat a send after uncertainty. Use received attempts;
no fabricated countdown, estimated send time or hidden retry button.

v1 has no outbox edit/retry events, and the planned REST mutations are not implemented
by the mock. Build a read-only list now; add controls only when a real interface and
scenario exist. A sending item is not safely cancellable merely because the UI
can hide it. Activity is backend-provided; do not fabricate success or persist
sensitive history in browser localStorage. Only show undo when `undoable` is true
and the connected agent supports it; use `activity.undo`, never local reversal.

## 6. Reducer and transport checklist

Use generated `WireAgentEvent` and `WireUIEvent`, with explicit `v` and `type`.
Pydantic remains the source of truth. Runtime-validate untrusted event data; generated
TypeScript alone cannot validate a WebSocket payload. Reject/handle unsupported
versions visibly without logging private payloads or session-token URLs.

| Input | Frontend state/action |
|---|---|
| `status` | Update state, connectivity, profile independently |
| `transcript.partial` | Replace current partial text, do not append each partial |
| `transcript.final` | Finalise text; speaker is optional; clear partial |
| `plan.preview` | Associate preview with `task_id`; offer correlated cancellation |
| `reply.text` | Render caption once per received event; show speech stop when relevant |
| `result.answer` | Render text/citations with unknown metadata preserved |
| `result.document` | Show title/path, without direct file opening |
| `confirm.request` / `cloud.approval_request` | Create separate pending request with received ID |
| `speaker.confirm_request` | Ask supplied question and await explicit response |
| `outbox.update` | Replace list with latest items; retain only backend-provided states |
| `activity.entry` | Add/upsert by ID within current session |
| `error` | Show supplied safe message and recovery option; retain useful local results |
| Transport loss | Show disconnected state; expire pending approvals; stop PTT; no automatic replay |

PTT must send start once on pointer/key down and stop once on release. Handle lost
pointer capture, blur/unmount and shortcut release to avoid stuck capture. Hotkey
choice is configurable after Windows conflict checks; do not hard-code a system-wide
shortcut without review. `tts.stop` stops playback; `task.cancel` needs an actual
known `task_id`. Do not invent a task ID during early listening. Scope Escape to
the dialog/task it can safely cancel, preserving backend cancellation semantics.

The mock restarts a scenario on each new connection and normally closes with 1000.
Do not reconnect-loop a completed fixture or replay stale sends. Production reconnect
and state resynchronisation still need a supported backend snapshot/recovery path.

## 7. Build order and acceptance

The frontend role file contains the live checkbox list. Begin with **F0 + one idle
workspace**: scaffold the frontend, apply tokens, connect authenticated mock health
and WebSocket, render status/transcript/captions and replay `policy_question`.
Then prioritise F1/F2 safety before richer work screens.

Useful committed fixtures: `voice_echo`, `policy_question`, `policy_not_found`,
`offline_policy_search`, `policy_search_paraphrase`, `open_policy_source`,
`gateway_retry_fallback`, `cloud_down_fallback`, `cloud_plan_execution`,
`email_reply_confirm_and_send`, `offline_send_then_reconnect`.
Run the mock's `--list` for current truth. A scenario may describe a future backend
path; mock success is not production feature readiness. Uncommitted backend work
in the shared workspace must not become a frontend dependency.

For every slice: unit-test reducer/control semantics, Playwright the appropriate
mock scenario and error/decline/cancel paths, run lint/types and check keyboard use.
For F5: test 900 × 600, 1280 × 800, 150% text, 200% Windows display scaling,
reduced motion and Windows high contrast. Focus must remain visible; dialogs must
scroll; all actions must be reachable. Use polite live regions for state/final
captions, avoid announcing every partial syllable, and reserve urgent announcements
for errors needing attention.

Before release, verify the real agent on Windows and let a non-technical staff
member try it. The design presentation is a specification and review aid, not the
production app or evidence that all screens work.

## 8. Team handoff boundaries

Frontend owns React/Tauri UI and UI tests. Backend owns transport behaviour,
credentials, microphone/audio, tools, model routing, files and data persistence.
Add a scenario and agree with the backend owner before adding contract fields or
REST capabilities. No `audio.level`, mute event, outbox mutation, document-open
extension or enrollment implementation is authorised merely by this design.

Keep this design handoff separate from concurrent backend work. The user has now
authorised publishing it through a normal pull request. Update this brief, tokens
and role checklist as implementation decisions and actual capabilities change.
