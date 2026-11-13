# ARIA agent pack

Everything an AI coding agent or developer needs to start building the voice-powered office assistant.

Start with `AGENTS.md`.

What is in the pack:

- `docs/PRD.md` product requirements
- `docs/TECH_SPEC.md` technical specification
- `docs/ARCHITECTURE.md` existing and planned files, backend module boundaries and phase order
- `docs/ROADMAP.md` phases, gates and the parallel work map
- `docs/API_CONTRACT.md` events and REST between UI and agent
- `docs/PROMPTS.md` prompt templates for the model
- `docs/TESTING.md` named unit tests, e2e scenarios and evaluations
- `docs/CICD.md` GitHub workflows
- `docs/DECISIONS.md` running decision log
- `agents/backend-ai.md`, `agents/frontend.md` role guides
- A small working skeleton: contract models, a mock agent, a tool base class, a pure router function and a gateway with auth and a spending cap, all with passing tests
- `.github/workflows` ready to run
- `tests/e2e/scenarios` starter scenario files

## Quick start

Install Python 3.11 and uv 0.13.7, then run from the repository root:

```sh
uv sync --locked --all-packages --all-extras
uv run --locked --all-packages --all-extras pre-commit install
uv run --locked --all-packages --all-extras python scripts/check_backend.py
uv run --locked --all-packages --all-extras python -m agent.mock --scenario policy_question
```

The mock agent binds to `127.0.0.1:8765`. The shared check command runs lint,
format checks, strict types, both services' unit tests with network sockets
blocked, and a read-only contract schema check. Pre-commit and backend CI use
that same command. Activate `.venv` if you want `uv` and the other installed
tools on your shell's PATH.

After an intentional contract update, regenerate the schema with
`uv run --locked --all-packages --all-extras python scripts/gen_contract.py`.
To update dependencies deliberately, use `uv lock` and review `uv.lock`;
normal installs use `--locked` so dependency declarations cannot silently drift.

Start with the phase order and file map in `docs/ARCHITECTURE.md`. Phase A is
still in progress. A coding agent will ask which role you are working as.

## Agent settings and diagnostic logs

The configuration module is `services/agent/src/agent/config.py`. It loads an
explicit TOML file with an `[agent]` table; use `config/agent.example.toml` as a
starting point and copy it to the ignored `config/agent.toml` for local values.
Known `ARIA_*` environment variables override file values; defaults fill unspecified fields.
It does not automatically load `.env` files. File paths are relative to the
TOML file; paths from the environment or defaults use the working directory.

```python
from pathlib import Path

from agent.config import load_settings
from agent.logging_config import configure_logging

settings = load_settings(Path("config/agent.toml"))
logger = configure_logging(settings.log_level)
logger.info("Settings loaded", extra={"event": "settings.loaded"})
```

Leave the gateway URL unset until a gateway is provisioned. A configured URL
must use HTTPS without credentials, queries or fragments. Supply the install
token through `ARIA_INSTALL_TOKEN`, never in TOML; the provider API key belongs
only on the gateway. `ARIA_DB_KEY_SOURCE` currently accepts only `os_vault`;
the encrypted store and vault implementation follow in A3.

The agent logger writes JSON metadata to stderr without creating log files. It
accepts fixed event names from `agent.logging_config.EVENTS`, UUID task IDs and
finite nonnegative `duration_ms`. Messages, arguments, exception text and other
extra fields are omitted so transcripts and credentials cannot be copied into
these diagnostics. Non-UUID IDs are omitted from logs; this does not change
the API contract. Real-agent startup will connect these modules in A4.
