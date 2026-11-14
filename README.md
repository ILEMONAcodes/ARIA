# ARIA agent pack

Everything an AI coding agent or developer needs to start building the voice-powered office assistant.

Start with `AGENTS.md`.

What is in the pack:

- `docs/PRD.md` product requirements
- `docs/TECH_SPEC.md` technical specification
- `docs/ARCHITECTURE.md` existing and planned files, backend module boundaries and phase order
- `docs/ROADMAP.md` phases, gates and the parallel work map
- `docs/API_CONTRACT.md` events and REST between UI and agent
- `docs/FRONTEND_HANDOFF.md` generated types, mock authentication and replay instructions
- `docs/PROMPTS.md` prompt templates for the model
- `docs/TESTING.md` named unit tests, e2e scenarios and evaluations
- `docs/CICD.md` GitHub workflows
- `docs/DECISIONS.md` running decision log
- `agents/backend-ai.md`, `agents/frontend.md` role guides
- A small working skeleton: contract models, a mock agent, a tool base class, a pure router function and a gateway with auth and a spending cap, all with passing tests
- `.github/workflows` ready to run
- `tests/e2e/scenarios` starter scenario files

## Quick start

Install Python 3.11, uv 0.13.7, Node 24 and Corepack, then run from the repository root:

```sh
uv sync --locked --all-packages --all-extras
cd scripts/contract
corepack pnpm install --frozen-lockfile
cd ../..
uv run --locked --all-packages --all-extras pre-commit install
uv run --locked --all-packages --all-extras python scripts/check_backend.py
node scripts/contract/check.mjs
uv run --locked --all-packages --all-extras python -m agent.mock --scenario policy_question
```

The mock agent binds to `127.0.0.1:8765` and prints a token-bearing WebSocket
URL; use that full URL. Its health endpoint requires the same token as a Bearer
header. See `docs/FRONTEND_HANDOFF.md` for example responses and replay rules.
The shared Python check command runs lint,
format checks, strict types, both services' unit tests with network sockets
blocked, and a read-only contract schema check. Pre-commit and backend CI use
that same command. A separate pre-commit/CI check verifies generated TypeScript
freshness and strict consumer compilation. Activate `.venv` if you want `uv` and the other installed
tools on your shell's PATH.

After an intentional contract update, regenerate the schema with
`uv run --locked --all-packages --all-extras python scripts/gen_contract.py`.
Then run `node scripts/contract/generate.mjs` and commit both generated formats.
To update dependencies deliberately, use `uv lock` and review `uv.lock`;
normal installs use `--locked` so dependency declarations cannot silently drift.

Start with the phase order and file map in `docs/ARCHITECTURE.md`. The Phase A
foundation gate passed backend/contract CI, the live mock replay and platform
checks, and its implementation is merged into main. A coding
agent will ask which role you are working as. The desktop UI is still a frontend F0 task.

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
the store uses a native Windows or macOS vault through its key-provider interface.

The agent logger writes JSON metadata to stderr without creating log files. It
accepts fixed event names from `agent.logging_config.EVENTS`, UUID task IDs and
finite nonnegative `duration_ms`. Messages, arguments, exception text and other
extra fields are omitted so transcripts and credentials cannot be copied into
these diagnostics. Non-UUID IDs are omitted from logs; this does not change
the API contract. Foundation startup now connects these modules through `agent.bootstrap`.

## Encrypted local storage

`services/agent/src/agent/store/` contains the SQLCipher connection factory,
ordered migrations, history repository and retention cleanup.
`agent.security.keys.OSVaultKeyProvider` retrieves a randomly generated 256-bit
database key from Windows Credential Manager or macOS Keychain. Unsupported,
plaintext or unavailable vault backends are rejected. Unit tests use fake
vaults and the real SQLCipher engine, without accessing real credentials.

The native SQLCipher driver is included in the locked Python dependencies.
There is no plaintext SQLite fallback. Opening a database checks the engine,
reads the schema with the key, applies migrations atomically, and purges
transcripts older than 30 days and activity entries older than 90 days. Records
at the exact cutoff remain. Timestamps are timezone-aware UTC microseconds.
Foundation startup repeats cleanup daily while the agent remains open.

The Phase A schema contains profiles, settings, transcripts and activity history.
Outbox, calendar and search tables will arrive with their feature migrations.
Applied migration checksums must match the application; newer or modified
migration histories are rejected instead of being rewritten.

Keys are associated with the resolved database path. Existing files must have
their matching vault key; a missing key never causes automatic replacement or
re-encryption. Moving or restoring a database requires preserving that key and
its association. Do not move a real database before a recovery workflow exists.
Retention removes records from the live database, not external backups.
Native vault authorization and Windows installation still require manual
platform smoke testing before deployment.

## Foundation startup and fake adapters

Run an offline lifecycle check without a microphone, database file, vault access
or cloud connection:

```sh
uv run --locked --all-packages --all-extras python -m agent --fake --check
```

To check the real encrypted store, use your local settings file instead:

```sh
uv run --locked --all-packages --all-extras python -m agent --settings config/agent.toml --check
```

The real check initializes the configured database using its native OS vault
key, applies migrations and purges expired history. With `--check` omitted, the
core stays running and repeats retention daily until interrupted. Shutdown
cancels cleanup, closes prepared adapters in reverse order, then closes storage.
Failure during startup also releases resources already acquired; diagnostics
omit exception text and configuration values.

This CLI checks foundations only. The separate Phase B voice CLI is documented
in [the voice pipeline guide](docs/VOICE_LOOP.md). It needs installed local
speech models and currently supports spoken echo only. The frontend can also use the scenario mock:
`python -m agent.mock --scenario policy_question`.

`agent.interfaces` defines the dependency boundaries and internal request/value
types. `agent.fakes` provides deterministic audio, VAD, wake-word, transcription,
identity, speech, planner, model, network, clock, key, storage and tool doubles.
They use fictional fixtures in memory and are explicitly injected in tests;
production failures never select them automatically. Model source text stays
in separate data blocks. The [Phase C3 integration guide](docs/GATEWAY_INTEGRATION.md)
documents the gateway client, approval and retry/fallback flow. Live provider
setup and voice/desktop UI integration remain pending.

The [local execution guide](docs/LOCAL_EXECUTION.md) covers the model-free text
service, confirmations, configured Windows app launching, ICS calendar reading
and a one-command fictional-calendar demo. Run `python -m agent.local --tools
config/local-tools.example.toml --command "calendar today"` inside the installed
workspace to try it without speech models or cloud setup.
