# E2E scenarios

Each file is used three ways: by the mock agent (frontend development), by the backend e2e tests, and by Playwright. See docs/TESTING.md section 8.3 for the full list of scenarios (E2E-01 to E2E-15). Add a file here before building any user-visible feature.

Format: `{"name": "...", "steps": [...]}`. A step is either `{"send": <agent event>, "delay_ms": n}` or `{"wait_for": "<ui event type>"}`. Events must match docs/API_CONTRACT.md.
