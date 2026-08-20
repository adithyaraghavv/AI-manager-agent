"""Unit tests for tools/check_consistency.py.

The linter is stdlib + pyyaml only, so these tests just build small ruleset
+ fixture-file pairs on disk and run the evaluator against them. No mocks.
"""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "tools" / "check_consistency.py"


def _load_linter(tmp_repo_root: Path):
    """Import check_consistency with REPO_ROOT rebound to a temp directory.

    The module resolves paths relative to a REPO_ROOT constant, so we import
    a fresh copy per-test and patch that constant. This lets each test build
    a hermetic fixture tree under `tmp_path`.
    """
    spec = importlib.util.spec_from_file_location(
        f"check_consistency_test_{tmp_repo_root.name}", MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.REPO_ROOT = tmp_repo_root
    return module


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")


def test_exact_mode_passes_when_dockerfile_matches(tmp_path: Path):
    linter = _load_linter(tmp_path)
    _write(
        tmp_path / "backend" / "Dockerfile",
        """
        FROM python:3.13-slim
        """,
    )
    rules = {
        "python_version": {
            "expected": "3.13",
            "mode": "exact",
            "checks": [
                {"path": "backend/Dockerfile", "regex": r"FROM python:(\d+\.\d+)"}
            ],
        }
    }
    reports = linter.evaluate(rules)
    assert len(reports) == 1
    assert not reports[0].failed
    assert reports[0].findings[0].status == "ok"


def test_exact_mode_detects_drift(tmp_path: Path):
    linter = _load_linter(tmp_path)
    _write(
        tmp_path / "backend" / "Dockerfile",
        """
        FROM python:3.14-slim
        """,
    )
    rules = {
        "python_version": {
            "expected": "3.13",
            "mode": "exact",
            "checks": [
                {"path": "backend/Dockerfile", "regex": r"FROM python:(\d+\.\d+)"}
            ],
        }
    }
    reports = linter.evaluate(rules)
    assert reports[0].failed
    drift = [f for f in reports[0].findings if f.status == "drift"][0]
    assert "3.14" in drift.detail
    assert "3.13" in drift.detail


def test_in_list_mode_accepts_matrix_containing_expected(tmp_path: Path):
    linter = _load_linter(tmp_path)
    _write(
        tmp_path / ".github" / "workflows" / "ci.yml",
        """
        jobs:
          backend:
            strategy:
              matrix:
                python-version: ["3.11", "3.12", "3.13"]
        """,
    )
    rules = {
        "python_matrix": {
            "expected": "3.13",
            "mode": "in_list",
            "checks": [
                {
                    "path": ".github/workflows/ci.yml",
                    "regex": r"python-version:\s*\[([^\]]+)\]",
                }
            ],
        }
    }
    reports = linter.evaluate(rules)
    assert not reports[0].failed
    ok = reports[0].findings[0]
    assert ok.status == "ok"
    assert "3.13" in ok.detail


def test_in_list_mode_flags_missing_value(tmp_path: Path):
    linter = _load_linter(tmp_path)
    _write(
        tmp_path / ".github" / "workflows" / "ci.yml",
        """
        jobs:
          backend:
            strategy:
              matrix:
                python-version: ["3.11", "3.12"]
        """,
    )
    rules = {
        "python_matrix": {
            "expected": "3.13",
            "mode": "in_list",
            "checks": [
                {
                    "path": ".github/workflows/ci.yml",
                    "regex": r"python-version:\s*\[([^\]]+)\]",
                }
            ],
        }
    }
    reports = linter.evaluate(rules)
    assert reports[0].failed


def test_glob_regex_scans_all_matching_files(tmp_path: Path):
    linter = _load_linter(tmp_path)
    _write(
        tmp_path / ".github" / "workflows" / "a.yml",
        """
        steps:
          - uses: actions/checkout@v4
        """,
    )
    _write(
        tmp_path / ".github" / "workflows" / "b.yml",
        """
        steps:
          - uses: actions/checkout@v3
        """,
    )
    rules = {
        "checkout_pin": {
            "expected": "v4",
            "mode": "exact",
            "checks": [
                {
                    "glob": ".github/workflows/*.yml",
                    "regex": r"uses:\s*actions/checkout@(v\d+)",
                }
            ],
        }
    }
    reports = linter.evaluate(rules)
    assert reports[0].failed
    drifts = [f for f in reports[0].findings if f.status == "drift"]
    assert len(drifts) == 1
    assert "b.yml" in drifts[0].detail


def test_yaml_pr_branches_passes_when_targets_main(tmp_path: Path):
    linter = _load_linter(tmp_path)
    _write(
        tmp_path / ".github" / "workflows" / "ci.yml",
        """
        name: CI
        on:
          pull_request:
            branches:
              - main
        jobs:
          test:
            runs-on: ubuntu-latest
            steps:
              - run: echo hi
        """,
    )
    rules = {
        "pr_branch": {
            "expected": "main",
            "mode": "yaml_pr_branches",
            "checks": [{"glob": ".github/workflows/*.yml"}],
        }
    }
    reports = linter.evaluate(rules)
    assert not reports[0].failed


def test_yaml_pr_branches_flags_wrong_branch(tmp_path: Path):
    linter = _load_linter(tmp_path)
    _write(
        tmp_path / ".github" / "workflows" / "ci.yml",
        """
        name: CI
        on:
          pull_request:
            branches:
              - pullingado
        jobs:
          test:
            runs-on: ubuntu-latest
            steps:
              - run: echo hi
        """,
    )
    rules = {
        "pr_branch": {
            "expected": "main",
            "mode": "yaml_pr_branches",
            "checks": [{"glob": ".github/workflows/*.yml"}],
        }
    }
    reports = linter.evaluate(rules)
    assert reports[0].failed


def test_load_rules_reads_yaml(tmp_path: Path):
    linter = _load_linter(tmp_path)
    ruleset = tmp_path / "rules.yaml"
    ruleset.write_text(
        yaml.safe_dump(
            {
                "rules": {
                    "sample": {
                        "expected": "1",
                        "mode": "exact",
                        "checks": [{"path": "x.txt", "regex": r"(\d)"}],
                    }
                }
            }
        )
    )
    loaded = linter._load_rules(ruleset)
    assert "sample" in loaded
