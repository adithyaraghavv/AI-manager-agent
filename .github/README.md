# .github/

GitHub configuration for the RAG-agent repo — CI workflows and Dependabot.

## Workflows

| Workflow | File | Triggers | Purpose |
|----------|------|----------|---------|
| CI | [`workflows/ci.yml`](workflows/ci.yml) | `push` (all branches), `pull_request` -> `main` | Build + test backend and frontend on every change |

### CI matrix

- **backend** — Python `3.11`, `3.12`, `3.13` on `ubuntu-latest`. Installs deps with `uv pip install --system -r backend/requirements.txt`, then `pytest -q backend/tests/`. `fail-fast: false` so every Python version reports.
- **frontend** — Node `20` on `ubuntu-latest`. Runs `npm ci`, `npm run lint` (oxlint), `npm run build`.

Both jobs run in parallel. No external services or secrets are required — backend tests are fixture-based (see `backend/tests/conftest.py`).

### Concurrency and permissions

- `concurrency.group = ${{ github.workflow }}-${{ github.ref }}`. `cancel-in-progress` is only on for non-default branches, so history on `main` stays intact.
- `permissions.contents: read` at the workflow level (least-privilege).

## Dependabot

[`dependabot.yml`](dependabot.yml) runs weekly for:

- `pip` in `/backend`
- `npm` in `/frontend`
- `github-actions` in `/`

Each raises up to 5 PRs at a time, labelled `dependencies` plus the ecosystem tag.

## Running locally

The CI is intentionally simple — you can reproduce it end-to-end on your laptop:

```bash
# Backend
uv pip install --system -r backend/requirements.txt
pytest -q backend/tests/

# Frontend
cd frontend
npm ci
npm run lint
npm run build
```

If you want to simulate the runner more closely, [`act`](https://github.com/nektos/act) will drive `ci.yml` inside a container:

```bash
act pull_request        # runs both jobs
act -j backend          # backend job only
act -j frontend         # frontend job only
```

`act` is optional — not required to develop.

## Why no bats tests?

The QA tests under `tests/workflows/` cover YAML structure. There is no shell logic in this CI (no helper scripts, no `run:` blocks with meaningful branching), so a `.bats` suite would have nothing to exercise. If a shell helper lands under `.github/` later, add bats coverage then.
