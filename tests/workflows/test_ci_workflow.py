"""Smoke tests for .github/workflows/ci.yml.

Guards against silent regressions in the CI contract: triggers, jobs, matrix,
runner, least-privilege permissions, and the "no secrets required" property.

PyYAML quirk: YAML's `on:` key is parsed as the boolean `True` under
`yaml.safe_load`. We normalize by preferring `True` when present.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    assert CI_WORKFLOW.exists(), f"missing workflow file: {CI_WORKFLOW}"
    with CI_WORKFLOW.open() as fh:
        return yaml.safe_load(fh)


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return CI_WORKFLOW.read_text()


def _get_on(workflow: dict) -> dict:
    # yaml.safe_load turns `on:` into the boolean True.
    if True in workflow:
        return workflow[True]
    return workflow["on"]


def test_workflow_has_name(workflow: dict) -> None:
    assert workflow.get("name"), "workflow must have a name"


def test_triggers_include_push_and_pull_request(workflow: dict) -> None:
    on = _get_on(workflow)
    assert "push" in on, "workflow must trigger on push"
    assert "pull_request" in on, "workflow must trigger on pull_request"


def test_pull_request_targets_default_branch(workflow: dict) -> None:
    on = _get_on(workflow)
    branches = on["pull_request"].get("branches") or []
    assert "main" in branches, (
        "pull_request should target the default branch (main)"
    )


def test_backend_and_frontend_jobs_exist(workflow: dict) -> None:
    jobs = workflow.get("jobs", {})
    assert "backend" in jobs, "missing 'backend' job"
    assert "frontend" in jobs, "missing 'frontend' job"


def test_both_jobs_run_on_ubuntu_latest(workflow: dict) -> None:
    for job_name in ("backend", "frontend"):
        assert workflow["jobs"][job_name]["runs-on"] == "ubuntu-latest", (
            f"job '{job_name}' must run on ubuntu-latest"
        )


def test_backend_matrix_covers_python_311_312_313(workflow: dict) -> None:
    strategy = workflow["jobs"]["backend"].get("strategy", {})
    matrix = strategy.get("matrix", {})
    versions = [str(v) for v in matrix.get("python-version", [])]
    for expected in ("3.11", "3.12", "3.13"):
        assert expected in versions, (
            f"backend matrix must include Python {expected}; got {versions}"
        )


def test_backend_matrix_fail_fast_disabled(workflow: dict) -> None:
    strategy = workflow["jobs"]["backend"].get("strategy", {})
    assert strategy.get("fail-fast") is False, (
        "fail-fast must be off so every Python version reports its status"
    )


def test_workflow_declares_least_privilege_permissions(workflow: dict) -> None:
    perms = workflow.get("permissions")
    assert perms is not None, "workflow must declare explicit permissions"
    assert isinstance(perms, dict), "permissions must be a mapping (least-privilege)"
    assert perms.get("contents") == "read", (
        "contents permission should be 'read' (least-privilege)"
    )


def test_workflow_has_concurrency_group(workflow: dict) -> None:
    concurrency = workflow.get("concurrency")
    assert concurrency, "workflow must define a concurrency group"
    assert "${{ github.workflow }}" in concurrency["group"]
    assert "${{ github.ref }}" in concurrency["group"]


def test_workflow_uses_no_secrets(workflow_text: str) -> None:
    # CI here is fully self-contained — flagging any secrets reference is
    # intentional so we notice if scope drifts.
    assert "secrets." not in workflow_text, (
        "CI must not reference any secrets — tests are fixture-based"
    )


def test_backend_installs_uv_and_runs_pytest(workflow: dict) -> None:
    steps = workflow["jobs"]["backend"]["steps"]
    uses_list = [s.get("uses", "") for s in steps]
    assert any("astral-sh/setup-uv" in u for u in uses_list), (
        "backend must install uv via astral-sh/setup-uv"
    )
    run_commands = " ".join(s.get("run", "") for s in steps)
    assert "uv pip install" in run_commands, "backend must install deps via uv"
    assert "pytest" in run_commands and "backend/tests" in run_commands, (
        "backend must invoke pytest against backend/tests"
    )


def test_frontend_runs_ci_lint_build(workflow: dict) -> None:
    steps = workflow["jobs"]["frontend"]["steps"]
    uses_list = [s.get("uses", "") for s in steps]
    assert any("actions/setup-node" in u for u in uses_list), (
        "frontend must use actions/setup-node"
    )
    run_commands = " ".join(s.get("run", "") for s in steps)
    assert "npm ci" in run_commands, "frontend must install via npm ci"
    assert "npm run lint" in run_commands, "frontend must run lint"
    assert "npm run build" in run_commands, "frontend must run build"


def test_frontend_setup_node_caches_on_lockfile(workflow: dict) -> None:
    steps = workflow["jobs"]["frontend"]["steps"]
    setup_node = next(
        (s for s in steps if "actions/setup-node" in s.get("uses", "")),
        None,
    )
    assert setup_node is not None
    cfg = setup_node.get("with", {})
    assert cfg.get("cache") == "npm"
    assert cfg.get("cache-dependency-path") == "frontend/package-lock.json"
