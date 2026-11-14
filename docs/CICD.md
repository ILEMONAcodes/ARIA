# CI/CD on GitHub

The workflow files are in `.github/workflows`. Each job skips itself cleanly when the code it tests does not exist yet, so the pipeline is green from the first commit.

## Branching
Trunk-based: short-lived branches from `main`, pull requests, one reviewer, squash merge. `main` is always releasable. Branch protection requires the checks marked (required).

## Workflows in `.github/workflows`

**`ci-backend.yml`** (on pull request and pushes to `main`, ubuntu-latest)
- Set up Python 3.11 and uv 0.13.7 with dependency cache
- Install both workspace members and development tools from `uv.lock` using `uv sync --locked --all-packages --all-extras`
- Run `scripts/check_backend.py`, also used locally and by pre-commit: ruff lint and format checks, mypy per service, pytest unit tests per service with network sockets blocked, and a read-only schema freshness check
- The required job is `ci-backend / check`; update branch protection if it required the former matrix/contract jobs
- `store-platform` additionally installs the locked dependencies on Windows and macOS and runs storage, key-provider, fake-adapter and startup lifecycle tests against real SQLCipher with fake vaults. Native OS vault authorization is reserved for manual platform smoke tests; unit tests never read real credentials.
- Windows asyncio uses a local TCP pair internally. The unit-test harness supplies only that ephemeral loopback pair; application socket creation and DNS remain blocked, with IPv4/IPv6 guard regression tests. No real mail, model or other service is contacted.
- `contract` installs pinned pnpm tools from `scripts/contract/pnpm-lock.yaml` on Node 24, checks generator failure paths and artifact freshness, and strictly compiles all fixture messages plus frontend consumer examples. It runs independently of the unfinished desktop app.
- The Python `check` job also runs the separate live localhost mock handoff after its network-blocked unit tests. This integration process uses only its own mock server and fictional session credentials.
- Coverage reporting and a minimum threshold remain to be agreed and implemented
- D2 source-opening tests also run in the platform matrix, using fake viewers
  and native-launch stubs only. The worker smoke checks source snapshot validation
  and rejection after a fictional file changes. No CI job opens a real viewer.
- D1 policy tests run in the platform matrix against real encrypted SQLCipher/FTS5
  and actual local PDF/DOCX/TXT readers; the worker smoke also checks temporary
  fictional policy indexing/search without native vault access or models.
- C6 session handoff tests also run in the platform matrix, including the real
  in-memory gateway with a fake provider and cancellation/replacement regressions.
  The worker smoke additionally checks session handoff into dependent workers.
- C5's step-result tests also run in the platform matrix; the real worker smoke
  includes a three-step binding chain and a rejected mutating preview.
- C4 local execution/calendar/text unit tests run in the platform matrix. The
  separate `smoke_execution.py` step uses real worker subprocesses and temporary
  markers to verify timeout/cancellation on Linux/Windows/macOS; it launches no
  application and uses no network or provider credentials.
- The platform matrix also runs C3's gateway client and cloud-flow tests with
  in-memory transports, including the real ASGI gateway with a fake provider.
  These do not require provider accounts, keys, live HTTP or paid model calls.
- Phase B's stub-engine voice/controller/transport tests also run in the platform
  matrix. `voice-windows` installs the opt-in locked speech dependency group and
  checks native imports only; it downloads no models and opens no audio device.
  WER, wake false accepts and real Windows audio/latency remain manual gates.

Install the local hook with `uv run --locked --all-packages --all-extras pre-commit install`.
The hook checks the complete backend, including tests, even for documentation
commits. Run it manually with `uv run --locked --all-packages --all-extras pre-commit run --all-files`.
A second hook runs `node scripts/contract/check.mjs` for contract, mock, scenario
and generator changes. Install Node 24 and the locked `scripts/contract` tools
before committing these files. The `contract` CI job is an additional required
foundation check. The live integration check is not part of the unit-test hook.
Other workflow files below remain scaffolding and still use their original pip
installation commands until their phase is implemented.

**`ci-frontend.yml`** (on pull request, ubuntu-latest)
- pnpm install with cache
- eslint, prettier check, `tsc --noEmit` (required)
- Vitest unit tests (required)
- Playwright against the mock agent (required)

**`e2e-agent.yml`** (nightly, and on pull requests with the label `e2e`)
- Python e2e scenarios with fixture audio, fake gateway and fake network
- Smoke scenarios must pass before a release

**`build-desktop.yml`** (on pull request touching `apps/desktop` or the agent packaging, windows-latest)
- Build the Python sidecar and the Tauri app to prove the installer still builds
- Upload the installer as a build artifact

**`security.yml`** (on pull request and weekly)
- `pip-audit` and `pnpm audit`
- Secret scanning (gitleaks), so no API key reaches the repo
- Dependency review

**`eval.yml`** (manual and weekly, not on every pull request)
- Runs the 30-question set, summary set and latency benchmark against the real model using a repository secret and a spending cap
- Posts the scores and fails if a metric drops past its threshold

**`release.yml`** (on a version tag, windows-latest)
- Build the sidecar and the Tauri installer, sign it, generate checksums
- Create a GitHub Release with the installer and checksums
- Models are attached as separate release assets with checksums

**`deploy-gateway.yml`** (on merge to `main` for staging; on a version tag for production)
- Build the Docker image, push to the registry, deploy
- Environments `staging` and `production`, with manual approval for production
- Run a health check and one smoke request after deploy; roll back on failure

## Secrets
Set as GitHub secrets, never in the repo: model API key (eval and gateway), registry and hosting credentials, code-signing certificate, test inbox OAuth credentials. The desktop app never contains the model API key.

## Caching and speed
Cache Python and pnpm dependencies. Keep fixture audio small and use the tiny Whisper model in CI. Cache downloaded models between runs.
