# Cross-config consistency check

## What this catches

`tools/check_consistency.py` reads `tools/consistency.yaml` and fails when a
pinned value drifts across the configs it appears in. The rules currently
enforced on `main`:

| Rule                          | Guards                                                                     |
| ----------------------------- | -------------------------------------------------------------------------- |
| `python_version_dockerfile`   | `backend/Dockerfile`'s `FROM python:` tag matches the pinned interpreter.  |
| `python_version_ci_matrix`    | The CI matrix in `.github/workflows/ci.yml` includes the pinned interpreter. |
| `node_version`                | Every workflow that uses `node-version: "…"` uses the same value.          |
| `action_checkout`             | `actions/checkout@vN` is pinned to the same major everywhere.              |
| `action_setup_python`         | `actions/setup-python@vN` is pinned to the same major everywhere.          |
| `action_setup_node`           | `actions/setup-node@vN` is pinned to the same major everywhere.            |
| `action_upload_artifact`      | `actions/upload-artifact@vN` is pinned to the same major everywhere.       |
| `trigger_branch_pull_request` | Every workflow that runs on `pull_request:` targets `main` only.           |

The linter runs in the `Checks` workflow with `--strict`, so drift blocks
PRs the same way a lint failure does.

## What this does NOT catch

- **Semantic drift.** If `backend/Dockerfile` pins `python:3.13` and the CI
  matrix also pins `3.13`, we're consistent — but nothing here checks that
  the code actually runs on 3.13. That's what the test suite is for.
- **Effective rule drift.** Alembic migrations, RBAC rules, feature flags, or
  any config where "same value in two places" is not the right question —
  a purpose-built checker (e.g. `check_ruleset_parity.py`) is the future-work
  answer. This linter deliberately stays on the "one string appears in N
  files" side of the line.
- **Transitive drift.** If action `foo/bar@v3` internally depends on a
  vulnerable version of something, the SBOM + audit jobs catch that; this
  linter only sees the top-level `@vN` pin.
- **Anything not in the ruleset.** Adding a new config file is a manual step
  (see below).

## How to add a rule

1. Edit `tools/consistency.yaml`.
2. Pick the simplest mode that expresses the constraint:
   - `exact` — every capture group must equal `expected`.
   - `in_list` — parse a bracketed literal (e.g. a matrix) and require it
     to contain `expected`.
   - `yaml_pr_branches` — special-case for workflow `on.pull_request.branches`.
3. Target files with either `path:` (single file) or `glob:` (many files).
4. For regex modes, use exactly one capture group. Anchor conservatively.
5. Run `python tools/check_consistency.py` locally. The rule must pass on
   `main` before it's merged. If the value it guards is currently drifted,
   add the rule as a `# TODO:` comment in `consistency.yaml` and fix the
   drift in a preceding PR instead.
6. If the new mode needs Python support beyond regex/PyYAML, extend the
   linter — it's intentionally short (< 300 LOC) to keep new modes cheap
   to add.

## When the check fails on your PR

Two paths, pick one:

1. **Fix the drift** (the usual answer). The failure message names the file
   and the mismatched value. Update whichever config is out of step and
   push again.
2. **Update the rule** (rarer, needs justification). If the expected value
   itself should change — e.g. we're intentionally bumping Python from
   3.13 to 3.14 — update every affected config *and* the `expected:` field
   in `consistency.yaml` in the same commit. The commit message must call
   out the version bump so reviewers can spot it in `git log`.

Do not silence the rule by removing it. If a rule is no longer meaningful,
delete it with a commit message that explains why.

## Running locally

```bash
python tools/check_consistency.py              # informational
python tools/check_consistency.py --strict     # CI mode; exits 1 on drift
python tools/check_consistency.py --json       # machine-readable output
python -m pytest tools/tests/                  # test the linter itself
```
