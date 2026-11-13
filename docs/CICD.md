# CI/CD on GitHub

The workflow files are in `.github/workflows`. Each job skips itself cleanly when the code it tests does not exist yet, so the pipeline is green from the first commit.

## Branching
Trunk-based: short-lived branches from `main`, pull requests, one reviewer, squash merge. `main` is always releasable. Branch protection requires the checks marked (required).

## Workflows in `.github/workflows`

**`ci-backend.yml`** (on pull request, ubuntu-latest)
- Set up Python 3.11 with dependency cache
- ruff (lint and format check) and mypy (required)
- pytest unit tests for `services/agent` and `services/gateway` with network sockets blocked (required)
- Coverage report, fail below the agreed threshold
- Check that generated contract files are up to date (required)

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
