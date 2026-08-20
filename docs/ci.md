# CI/CD Lifecycle

This repo ships four GitHub Actions workflows that together cover build,
test, security hygiene, versioning, and container publishing.

| Workflow       | File                                   | Triggers                                  |
| -------------- | -------------------------------------- | ----------------------------------------- |
| Build & Test   | `.github/workflows/ci.yml`             | push to any branch, PRs into `main`       |
| Checks         | `.github/workflows/checks.yml`         | push to `main`, PRs into `main`           |
| Release Please | `.github/workflows/release-please.yml` | push to `main`                            |
| Package        | `.github/workflows/package.yml`        | `release: published`, `workflow_dispatch` |

## Build & Test — `ci.yml`

Compiles and tests the backend across Python 3.11 / 3.12 / 3.13, then
lints and builds the frontend with Node 20. This is the gate that blocks
merges: it must be green.

- Backend: `uv pip install --system -r backend/requirements.txt` then
  `pytest -q backend/tests/`.
- Frontend: `npm ci` -> `npm run lint` -> `npm run build`.

**When it fails:** reproduce locally with `pytest -q backend/tests/` or
`cd frontend && npm ci && npm run lint && npm run build`. Fix and push.

## Checks — `checks.yml`

Parallel hygiene pass. Each job is time-boxed to 15 minutes and runs with
read-only repo permissions.

- `lint-actions` — `actionlint` on every workflow file. Hard fail.
- `lint-shell` — `shellcheck` on every `*.sh`. Hard fail.
- `lint-docker` — `hadolint` on any `Dockerfile*` (skips cleanly if none).
  Hard fail.
- `secrets-scan` — `gitleaks` with `--redact`. Hard fail; do NOT commit
  the raw secret in the fix, rotate it and scrub history.
- `python-audit` — `pip-audit` against `backend/requirements.txt`. Soft
  fail: emits a `::warning::` annotation so the run stays green but the
  finding is visible in the PR.
- `js-audit` — `npm audit --production --audit-level=high` in
  `frontend/`. Soft fail with a warning annotation.
- `sbom` — `anchore/sbom-action` produces an SPDX JSON SBOM uploaded as
  the `sbom-spdx` artifact.

**When it fails:**

- `actionlint` / `shellcheck` / `hadolint`: the annotation points at the
  exact line. Fix and push.
- `gitleaks`: **rotate the credential first**, then remove it from the
  diff (and history if it landed). Never "just delete the line" and push.
- Audit warnings: bump the affected dependency in `requirements.txt` or
  `frontend/package.json`. If the CVE has no fix yet, note it in the PR
  description and move on — audits are advisory here.

## Release Please — `release-please.yml`

Reads `release-please-config.json` and `.release-please-manifest.json`
and, on every push to `main`, either opens or updates a "release
PR" whose body is the auto-generated changelog. Merging that PR:

1. Bumps `backend/pyproject.toml` `version`.
2. Updates `.release-please-manifest.json`.
3. Writes `CHANGELOG.md`.
4. Creates a git tag (e.g. `v0.2.0`) and a GitHub release.

The release event is what fans out to `package.yml`.

**When it fails:** the workflow is almost always failing because a
commit message is not a valid Conventional Commit. Fix future commits.
Fix past ones only if the release PR contents look wrong.

## Package — `package.yml`

Builds a multi-arch (`linux/amd64`, `linux/arm64`) image of the backend
using `backend/Dockerfile`, then pushes it to
`ghcr.io/<owner>/<repo>/backend` tagged with the release version and
`latest`. Uses `docker/setup-qemu-action`, `docker/setup-buildx-action`,
`docker/login-action` (against GHCR using the built-in `GITHUB_TOKEN`),
and `docker/build-push-action` with provenance + SBOM attestations
enabled.

Also exposed via `workflow_dispatch` so you can re-publish an image
without cutting a new release. The workflow takes an optional `tag`
input; if omitted, it falls back to `manual-<shortsha>`.

**When it fails:**

- Auth error on push: confirm the repo's GHCR package (created on the
  first successful push) allows the `GITHUB_TOKEN` to write.
- Buildx / QEMU flakiness: re-run the failed job.
- Dockerfile error: fix `backend/Dockerfile`, land it, cut a new
  release (or `workflow_dispatch` a rebuild).

## Cutting a release

1. Land changes on `main` using [Conventional
   Commits](https://www.conventionalcommits.org/) (`feat:`, `fix:`,
   `ci:`, `chore:`, `docs:`, etc.).
2. `release-please.yml` opens/updates a "chore: release X.Y.Z" PR
   automatically. Review the generated changelog.
3. Merge the release PR. That creates the git tag and the GitHub
   release.
4. The `release: published` event triggers `package.yml`, which builds
   and publishes the multi-arch backend image to GHCR under the new
   tag (and updates `:latest`).

No manual tagging, no manual changelog editing, no manual `docker
build`.
