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
- `store-platform` additionally installs the locked dependencies on Windows and macOS and runs storage/key-provider tests against real SQLCipher with fake vaults. Native OS vault authorization is reserved for manual platform smoke tests; unit tests never read real credentials.
- Coverage reporting and a minimum threshold remain to be agreed and implemented

Install the local hook with `uv run --locked --all-packages --all-extras pre-commit install`.
The hook checks the complete backend, including tests, even for documentation
commits. Run it manually with `uv run --locked --all-packages --all-extras pre-commit run --all-files`.
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
