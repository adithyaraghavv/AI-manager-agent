<!--
Marp slide source. Render with:
    npx @marp-team/marp-cli slides.md --pdf
    npx @marp-team/marp-cli slides.md --html
    npx @marp-team/marp-cli slides.md --pptx
-->
---
marp: true
theme: default
paginate: true
size: 16:9
title: CI/CD lifecycle + pre-commit hooks
description: Announcement deck for RAG-agent — PR #2 and PR #48
author: Platform team
header: "RAG-agent · Platform · 2026-08-17"
footer: "Questions → #platform"
style: |
  section { font-family: -apple-system, "Segoe UI", sans-serif; }
  section h1 { color: #1a4480; }
  section h2 { color: #1a4480; border-bottom: 2px solid #dfe1e5; padding-bottom: 4px; }
  code, pre { font-family: "SF Mono", "Consolas", monospace; }
  table { font-size: 0.75em; border-collapse: collapse; }
  th { background: #eef; text-align: left; padding: 6px 10px; }
  td { padding: 6px 10px; border-top: 1px solid #dfe1e5; }
  .small { font-size: 0.7em; color: #555; }
---

<!-- _class: lead -->

# CI/CD lifecycle + pre-commit hooks
## RAG-agent · Platform update · 2026-08-17

Two PRs, one story.

---

## TL;DR

- Every PR runs a full check slate — lint, tests, secrets, audits, SBOM.
- Every merge to `pullingado` can cut a release without anyone touching a version file.
- Local commits run the same lint / format / secret-scan rules — no more style nits caught in review.
- Contributors write Conventional Commits; the changelog writes itself.

<div class="small">Shipping in PR #2 (CI/CD lifecycle) and PR #48 (pre-commit hooks).</div>

---

## What CI runs on every PR

| Workflow | What it catches |
|---|---|
| `pr-checks.yml` | Backend regression + feature tests + frontend build |
| `checks.yml` | actionlint, shellcheck, hadolint, gitleaks, `uv pip audit`, `npm audit`, SBOM |
| `pre-commit-ci.yml` | The same hook stack that runs locally — safety net |

All actions pinned to explicit versions. Read-only permissions by default. 15-minute timeouts. Concurrency groups cancel stale runs.

---

## What runs on merge to `pullingado`

- **`release-please.yml`** — reads Conventional Commits since last release, opens (or updates) a "chore(main): release X.Y.Z" PR with version bump + generated `CHANGELOG.md`.
- **`package.yml`** — fires when a GitHub release is published. Builds a multi-arch (`linux/amd64,linux/arm64`) container of the backend and pushes to `ghcr.io/<repo>/backend`.

No manual `git tag`. No manual changelog. No manual `docker push`.

---

## The pre-commit hook stack — part 1

| Hook | Scope | What it does |
|---|---|---|
| `trailing-whitespace` + `end-of-file-fixer` | all | Whitespace hygiene |
| `check-yaml` + `check-json` | all | Parse-time syntax check |
| `check-added-large-files` (500 KB) | all | Blocks accidental binaries |
| `check-merge-conflict` | all | Blocks unresolved markers |
| `ruff` + `ruff-format` | `backend/` | Python lint + format |
| `prettier` | `frontend/`, `docs/` | JS / CSS / MD / YAML format |

---

## The pre-commit hook stack — part 2

| Hook | Scope | What it does |
|---|---|---|
| `codespell` | all | Typos in code and prose |
| `gitleaks` | all | Secrets scan (keys, tokens) |
| `hadolint` | `Dockerfile*` | Docker best-practice lint |
| `markdownlint` | `*.md` | Markdown style (tuned for Docusaurus) |
| `conventional-pre-commit` | commit-msg | Enforces `type(scope): subject` |

Plus `.editorconfig` and `.markdownlint.yaml` so your editor agrees with the hooks.

---

## Set it up

```bash
uv tool install pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type commit-msg
```

Run against the whole repo once:

```bash
pre-commit run --all-files
```

Update to newer hook versions whenever:

```bash
pre-commit autoupdate
```

---

## Conventional Commits — cheat sheet

| Prefix | When | Semver bump |
|---|---|---|
| `feat:` | New user-visible feature | minor |
| `fix:` | Bug fix | patch |
| `perf:` | Perf improvement | patch |
| `docs:` | Docs only | none |
| `chore:` | Config / deps / tooling | none |
| `ci:` | CI/CD changes | none |
| `refactor:` | Behaviour-preserving refactor | none |
| `test:` | Tests only | none |
| `BREAKING CHANGE:` in body | Any breaking API change | major |

---

## The release flow

```
merge conv-commits to `pullingado`
              |
              v
      release-please opens
   "chore(main): release X.Y.Z"
              |
       [ you review + merge ]
              |
              v
       git tag + GitHub release
              |
              v
     package.yml builds container
     and pushes to ghcr.io/<repo>
```

If commit history has the right shape, the release ships itself.

---

## When something fails — quick reference

| Failure | Usual fix |
|---|---|
| `checks / lint-actions` red | Run `actionlint` locally; fix reported issues |
| `checks / secrets-scan` red | Rotate credential now; ping platform to purge |
| `pre-commit-ci` red | Install pre-commit so it catches on commit, not in CI |
| `release-please` not opening a PR | Check commit messages follow Conventional Commits |
| `package` job red | Confirm `docker build backend/` works locally |

---

<!-- _class: lead -->

## Related PRs

- **PR #2** — CI/CD lifecycle
- **PR #48** — pre-commit hooks + dev-setup docs
- **PR #49** — dev/prd deployment (docker-compose + Makefile + ADO pipeline; ansible layer in flight)

Questions → file an issue with the `ci` label, or ping `#platform`.
