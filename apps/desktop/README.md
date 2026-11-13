# apps/desktop

Tauri shell and React/TypeScript UI. Owned by the frontend engineer.

Not scaffolded yet. Start from agents/frontend.md phase F0:

1. Create the Vite + React + TypeScript app here and add the Tauri shell (`src-tauri/`).
2. Add scripts: `gen:types` (turn `src/contract/schema.json` into TypeScript types with json-schema-to-typescript), `lint`, `typecheck`, `test` (Vitest), `e2e` (Playwright), `tauri`.
3. Run the mock agent from `services/agent`: `python -m agent.mock --scenario policy_question`.
4. Build against `ws://127.0.0.1:8765/ws` first, then the real agent.

The CI workflows in `.github/workflows` start running the frontend jobs as soon as `apps/desktop/package.json` exists.
