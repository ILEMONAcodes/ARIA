# Decisions

Add one line here whenever we make a choice or something surprises us. Move requirement IDs between phases only through a decision recorded here.

## Decided

1. **No dedicated brain PC.** A desktop app on each staff PC does the voice loop, search, files and outbox. A small cloud gateway handles the language model. Why: nobody has to own or set up a shared machine.
2. **Python backend, Tauri desktop shell, browser-tech UI.** Why: best ML library support, one UI codebase.
3. **The language model outputs a validated plan, never direct actions.** Why: safety and testability.
4. **Confirmation required for external sends and deletes.** Why: speaker ID is not strong authentication.
5. **Gemma 4 is the language model, called through an API.** Supervisor's choice. Default is 26B A4B through the gateway. Why: cheapest and fastest of the large models, native function calling, no GPU to run ourselves.
6. **Local profile (on-device Gemma 4 E4B or E2B) is later, not MVP.** Why: needs more RAM than most staff PCs have, and quality on small models must be tested first.
7. **Minimum 8 GB RAM per staff PC.** A 2 GB machine cannot run the app locally.
8. **Keep Whisper for speech-to-text** until a test shows Gemma 4 audio input does better on Nigerian-accented English.
9. **RAG for policies, circulars and summaries, with cited answers.**
10. **Use the existing `ILEMONAcodes/ARIA` GitHub repository.** Initialize the supplied project pack on `main` and connect it as `origin`; do not create a second repository.
11. **Document the backend file architecture before expanding the skeleton.** `docs/ARCHITECTURE.md` separates existing starter files from planned phase A–I modules, defines runtime/security boundaries and lists phase gates. Planned modules are created only when their phase is reached; the UI contract remains unchanged.
12. **Phase A uses a uv workspace and one committed lockfile.** Keep the agent and gateway as separate packages, share a Python 3.11 development environment, and run the same lint, format, type, offline unit-test and contract checks locally, in pre-commit and in backend CI. Later deployment workflows will adopt the lockfile when their packaging is implemented.

## To decide after testing

- Gemma 4 API provider and spending cap
- 26B A4B or 31B, based on the 30-task quality test
- Where the gateway is hosted
- Whether to add a thin-client mode for very low-RAM PCs
- Chunk size and number of retrieved passages for policy search

## Learned

(add lines as we go)
