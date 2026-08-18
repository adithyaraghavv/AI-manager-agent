# Local Dev Setup

This guide gets a new contributor from a fresh clone to a working local
environment with all pre-commit hooks wired up.

## Prerequisites

Install these once per machine:

- **[uv](https://docs.astral.sh/uv/)** — Python toolchain (venv, pip,
  and project manager). Install via
  `curl -LsSf https://astral.sh/uv/install.sh | sh` or `brew install uv`.
- **[Node.js](https://nodejs.org/)** — 20.x or newer, needed for the
  frontend workspace and for Prettier / markdownlint hooks that run
  under Node. Install via `brew install node` or `nvm install 20`.
- **[pre-commit](https://pre-commit.com/)** — orchestrates all the
  lint/format hooks. We install it as a `uv` tool so it lives on your
  `PATH` without polluting a project venv (see next section).

## Install the hooks

From the repo root, run:

```bash
uv tool install pre-commit
pre-commit install --install-hooks
pre-commit install --hook-type commit-msg
```

What each line does:

1. `uv tool install pre-commit` — puts `pre-commit` on your `PATH`.
2. `pre-commit install --install-hooks` — installs the standard
   `pre-commit` git hook and pre-downloads every hook environment so
   your first commit isn't slow.
3. `pre-commit install --hook-type commit-msg` — installs the
   `commit-msg` hook, which is what runs
   [Conventional Commits](https://www.conventionalcommits.org/)
   validation on your commit message.

After this, every `git commit` will automatically run the configured
hooks against your staged changes.

## Run hooks manually

To lint the whole repo (useful before opening a PR, or right after
pulling `main`):

```bash
pre-commit run --all-files
```

To run a single hook against all files (e.g. just `ruff`):

```bash
pre-commit run ruff --all-files
```

To run hooks only against files staged for the next commit:

```bash
pre-commit run
```

## Skipping hooks in emergencies

Sometimes you genuinely need to bypass a hook — for example, when
committing a work-in-progress fix during an incident and the codespell
dictionary is flagging a legitimate term. Use the `SKIP` env var, which
takes a comma-separated list of hook ids:

```bash
SKIP=codespell,ruff git commit -m "fix: patch prod hotpath"
```

This should be rare. If you find yourself reaching for `SKIP` more than
occasionally, the right fix is usually to update the hook config (add
the word to the codespell ignore list, tune a ruff rule, etc.) rather
than to keep bypassing it. CI runs the same hooks against your PR, so
skipped violations will surface there anyway.

## Updating hook versions

`pre-commit` pins every hook repo to a specific `rev`. To bump them all
to the latest tagged release:

```bash
pre-commit autoupdate
```

Review the diff to `.pre-commit-config.yaml`, run
`pre-commit run --all-files` to make sure nothing new is flagged, and
open a PR with the version bumps.
