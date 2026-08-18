"""Smoke tests for .github/dependabot.yml.

We keep the pip/npm/github-actions trio wired up so drift in any one ecosystem
gets flagged early rather than after a supply-chain incident.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPENDABOT = REPO_ROOT / ".github" / "dependabot.yml"


@pytest.fixture(scope="module")
def config() -> dict:
    assert DEPENDABOT.exists(), f"missing dependabot config: {DEPENDABOT}"
    with DEPENDABOT.open() as fh:
        return yaml.safe_load(fh)


def test_dependabot_version_is_2(config: dict) -> None:
    assert config.get("version") == 2, "dependabot config must be schema version 2"


def test_dependabot_has_updates(config: dict) -> None:
    assert isinstance(config.get("updates"), list) and config["updates"], (
        "dependabot must declare at least one updates entry"
    )


def test_dependabot_covers_pip_npm_github_actions(config: dict) -> None:
    ecosystems = {u.get("package-ecosystem") for u in config["updates"]}
    for expected in ("pip", "npm", "github-actions"):
        assert expected in ecosystems, (
            f"dependabot must cover '{expected}'; found {sorted(ecosystems)}"
        )


def test_pip_points_at_backend_directory(config: dict) -> None:
    pip = next(u for u in config["updates"] if u["package-ecosystem"] == "pip")
    assert pip.get("directory") == "/backend", (
        "pip updates should scan /backend where requirements.txt lives"
    )


def test_npm_points_at_frontend_directory(config: dict) -> None:
    npm = next(u for u in config["updates"] if u["package-ecosystem"] == "npm")
    assert npm.get("directory") == "/frontend", (
        "npm updates should scan /frontend where package.json lives"
    )


def test_github_actions_points_at_root(config: dict) -> None:
    gha = next(
        u for u in config["updates"] if u["package-ecosystem"] == "github-actions"
    )
    assert gha.get("directory") == "/", (
        "github-actions updates track workflows under /.github/workflows"
    )


def test_all_updates_are_weekly(config: dict) -> None:
    for entry in config["updates"]:
        schedule = entry.get("schedule", {})
        assert schedule.get("interval") == "weekly", (
            f"expected weekly cadence, got {schedule!r} for "
            f"{entry.get('package-ecosystem')}"
        )
