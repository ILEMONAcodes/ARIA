# ARIA inspiration — reviewed design direction

Reviewed: 14 November 2026. This folder preserves the user's starting references.
The implementation brief and presentation now live outside this reference folder:

- [Design presentation](../design/presentation.html)
- [Shareable PDF](../design/ARIA-desktop-design.pdf)
- [Frontend design brief](../../../docs/FRONTEND_DESIGN.md)
- [Tokens and SVG assets](../design/README.md)

## What was supplied

The JPG contains government/NITDA/NCAIR logos. Use it as a colour/identity reference,
not an app layout or a claim of endorsement. It is now a regular image file, copied
byte-for-byte from the original Telegram shortcut so it travels with the repo.
No official logo has been redrawn or incorporated into ARIA's new mark.

The earlier blueprint described dark voice assistants, a welcoming greeting,
suggestion cards and a green listening ring. Those other screenshots were not
present here during review. Their described qualities informed the proposal;
we do not claim to have inspected missing images.

## Recommended refinement

**Forest & Paper:** a deep-green sidebar, warm-white task area, calm voice motif,
readable evidence cards and distinct consent dialogs. Use the new **Signal A** logo
from `../design/assets/`. Keep `aria-logo-concept.svg` as an earlier ring-and-wave
exploration; it is not the current implementation asset.

## Corrections to the earlier blueprint

- There is no v1 `audio.level` event. Animate a deterministic state indicator; never
  read the microphone in the frontend to obtain amplitude.
- Do not add unsupported requirement IDs or meeting transcription, phone clients,
  extra admin tools or other capabilities outside the PRD.
- Do not claim official NITDA endorsement or formally verified brand colours.
- Do not guess identity, document dates/pages, delivery status or source confidence.
- Cloud upload approval and action confirmation remain separate.
- Outbox mutations, general mute, profile APIs and document opening need real
  backend interfaces before their controls can become functional.

Follow `docs/PRD.md`, `docs/API_CONTRACT.md` and the new frontend brief if older
reference artwork suggests a conflicting interaction.
