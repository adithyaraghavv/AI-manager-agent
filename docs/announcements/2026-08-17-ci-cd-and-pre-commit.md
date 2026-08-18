---
title: "New: CI/CD lifecycle and pre-commit hooks"
date: 2026-08-17
authors: [platform]
tags: [ci, release, tooling]
---

# What's new: CI/CD lifecycle + pre-commit hooks

**TL;DR** — every PR to `pullingado` now runs a full slate of automated checks. Merges cut versions and publish container images without anyone reaching for the release console. Your local commits get the same lint / format / secret-scan rules so nothing gets caught in review that could have been caught on your laptop. Contributors write [Conventional Commits](https://www.conventionalcommits.org/); the changelog writes itself.

Two PRs, one story:

- **PR #2 — CI/CD lifecycle** — the pipelines that live in `.github/workflows/`.
- **PR #48 — pre-commit hooks** — the same rules, applied on your machine before you push.

---

## What CI runs on every PR

| Workflow | Trigger | What it catches |
|---|---|---|
| `pr-checks.yml` | PR to `pullingado` | Backend regression + feature tests + frontend build (already in place) |
| `checks.yml` | PR + push to `pullingado` | actionlint, shellcheck, hadolint, gitleaks, `uv pip audit`, `npm audit`, SPDX SBOM |
| `pre-commit-ci.yml` | PR + push to `pullingado` | Same hook stack that runs locally — as a safety net for contributors who haven't installed pre-commit |
| `release-please.yml` | Push to `pullingado` | Opens/updates a "chore(main): release X.Y.Z" PR based on Conventional Commits since the last release |
| `package.yml` | GitHub release published | Builds a multi-arch (`linux/amd64,linux/arm64`) container of the backend and pushes it to `ghcr.io/<repo>/backend` tagged with the version and `latest` |

All third-party actions are pinned to explicit version tags. Every job has a 15-minute timeout and a `concurrency` group so re-pushes cancel stale runs. Permissions default to read-only, and the two jobs that need write scope (release-please and container publish) declare exactly what they need.

---

## The pre-commit hook stack (PR #48)

Runs on `git commit` locally, and on every PR via `pre-commit-ci.yml` in CI.

| Hook | Scope | What it does |
|---|---|---|
| `trailing-whitespace`, `end-of-file-fixer`, `mixed-line-ending` | all files | Whitespace hygiene |
| `check-yaml`, `check-json` | all files | Parse-time syntax check |
| `check-added-large-files` (500 KB max) | all files | Blocks accidentally committed binaries |
| `check-merge-conflict` | all files | Blocks unresolved conflict markers |
| `ruff` (lint) + `ruff-format` | `backend/` | Python lint + format |
| `prettier` | `frontend/`, `docs/` | JS/CSS/MD/YAML formatting |
| `codespell` | all files | Common typos in code and prose |
| `gitleaks` | all files | Secrets detection (API keys, tokens, private keys) |
| `hadolint` | `Dockerfile*` | Docker best-practice lint |
| `markdownlint` | `*.md` | Markdown style (with MD013 line-length and MD033 inline-HTML disabled for Docusaurus) |
| `conventional-pre-commit` | commit message | Enforces `type(scope): subject` format |

Companion files: `.editorconfig` (so your editor matches the hooks before you even save) and `.markdownlint.yaml` (tuned for our Docusaurus setup).

---

## Set it up in 30 seconds

```bash
uv tool install pre-commit
pre-commit install --install-hooks         # runs on every git commit
pre-commit install --hook-type commit-msg  # enforces conventional-commits
```

Run it against the whole repo once, so you know what the baseline looks like:

```bash
pre-commit run --all-files
```

You can update to newer hook versions whenever you want:

```bash
pre-commit autoupdate
```

If a hook blocks something you're **certain** is fine, skip that one hook for that one commit (rare — flag it in the PR description):

```bash
SKIP=hookid git commit -m "…"
```

---

## Conventional Commits — quick reference

The `conventional-pre-commit` hook enforces this format. `release-please` reads it to decide the semver bump and to write the changelog.

| Prefix | When to use | Bumps |
|---|---|---|
| `feat:` | New user-visible feature | minor |
| `fix:` | Bug fix | patch |
| `docs:` | Docs only | none |
| `chore:` | Config, deps, tooling — no user impact | none |
| `ci:` | CI/CD pipeline changes | none |
| `refactor:` | Behaviour-preserving code change | none |
| `test:` | Tests only | none |
| `perf:` | Performance improvement | patch |
| `BREAKING CHANGE:` in body | Any breaking API change | major |

Optional scope: `feat(auth): support device-code flow`.

---

## Cutting a release

1. Merge Conventional-Commits PRs into `pullingado`.
2. `release-please` detects the new commits and opens (or updates) a **release PR** titled `chore(main): release X.Y.Z`. It contains the version bump in `pyproject.toml`, the manifest update, and a generated `CHANGELOG.md`.
3. Review that PR and merge it. On merge, `release-please` creates the git tag and the GitHub release.
4. The `package.yml` workflow fires on the release event and publishes the multi-arch container image to GHCR.

No manual `git tag`. No manual changelog. If the commit history has the right shape, the release ships itself.

---

## When something fails

| Failure | First place to look | Usual fix |
|---|---|---|
| `checks / lint-actions` red | Your changed workflow YAML | Run `actionlint` locally; fix reported issues |
| `checks / secrets-scan` red | Recent commits | Rotate the leaked credential immediately, then `git filter-repo` to purge (ping platform) |
| `checks / python-audit` warning | `backend/requirements.txt` | Update the vulnerable dep or add an exception if unfixable |
| `pre-commit-ci` red | The failing hook's docs | Install pre-commit locally so this catches on commit, not in CI |
| `release-please` isn't opening a PR | Your commit messages | Check they follow Conventional Commits — the hook enforces this on new commits, older ones may not |
| `package` job red | Backend Dockerfile | Confirm `backend/Dockerfile` builds locally: `docker build backend/` |

---

## Related PRs

- **PR #2** — the CI/CD lifecycle itself
- **PR #48** — the pre-commit hook stack + local dev docs
- **PR #49** — dev/prd deployment stack (docker-compose + Makefile + ADO pipeline; ansible layer coming)

Questions? File an issue with the `ci` label, or ping `#platform` on Slack.
