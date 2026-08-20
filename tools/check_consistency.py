#!/usr/bin/env python3
"""Cross-config consistency linter.

Reads a ruleset (default: tools/consistency.yaml) and verifies that pinned
versions, action shas, and trigger branches stay in lockstep across configs
(Dockerfile, CI workflows, etc.). Catches drift that would otherwise only
show up at build/deploy time.

Design notes
------------
* Zero deps beyond the stdlib and PyYAML. `tomllib` is stdlib on 3.11+.
* Every rule is regex- or YAML-shape-based. The linter never executes any
  of the configs it inspects.
* Ships intentionally small (< 300 LOC). Add new rule modes here only when
  a regex genuinely cannot express the constraint.

Exit codes
----------
* 0 — every enforced rule passes.
* 1 — one or more rules reports DRIFT (or, with --strict, warnings).
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RULES = REPO_ROOT / "tools" / "consistency.yaml"

# Modes that require a captured regex group.
_REGEX_MODES = {"exact", "in_list"}
# Modes that pull structured data straight from the file (no regex).
_STRUCTURED_MODES = {"yaml_pr_branches"}
ALL_MODES = _REGEX_MODES | _STRUCTURED_MODES


@dataclass
class Finding:
    """One observation for a rule — either a pass, a drift, or a warning."""

    rule: str
    status: str  # "ok" | "drift" | "warn"
    detail: str
    file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "status": self.status,
            "detail": self.detail,
            "file": self.file,
        }


@dataclass
class RuleReport:
    rule: str
    expected: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def failed(self) -> bool:
        return any(f.status == "drift" for f in self.findings)

    @property
    def warned(self) -> bool:
        return any(f.status == "warn" for f in self.findings)


def _load_rules(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    rules = data.get("rules") or {}
    if not isinstance(rules, dict):
        raise SystemExit(f"consistency ruleset at {path} has no 'rules' mapping")
    return rules


def _resolve_files(check: dict[str, Any]) -> list[Path]:
    """Return the concrete files a single check should scan."""
    if "path" in check:
        return [REPO_ROOT / check["path"]]
    pattern = check.get("glob") or check.get("checks_all_matching")
    if not pattern:
        raise ValueError(f"check missing 'path' or 'glob': {check}")
    matches = sorted(glob.glob(str(REPO_ROOT / pattern)))
    return [Path(m) for m in matches]


def _check_regex(
    rule_name: str,
    expected: str,
    mode: str,
    file_path: Path,
    regex: str,
) -> list[Finding]:
    """Apply a regex-based check to a single file."""
    findings: list[Finding] = []
    rel = str(file_path.relative_to(REPO_ROOT))
    try:
        text = file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [Finding(rule_name, "warn", f"file missing: {rel}", rel)]

    matches = re.findall(regex, text)
    if not matches:
        # Not every workflow uses every action — silent skip is correct here.
        return findings

    for raw in matches:
        # `re.findall` yields str for single-group patterns, tuple for many.
        captured = raw if isinstance(raw, str) else raw[0]
        if mode == "exact":
            if captured == expected:
                findings.append(
                    Finding(rule_name, "ok", f"{captured} in {rel}", rel)
                )
            else:
                findings.append(
                    Finding(
                        rule_name,
                        "drift",
                        f"{rel}: got '{captured}', expected '{expected}'",
                        rel,
                    )
                )
        elif mode == "in_list":
            items = _parse_list_literal(captured)
            if expected in items:
                findings.append(
                    Finding(
                        rule_name,
                        "ok",
                        f"{rel}: list {items} contains '{expected}'",
                        rel,
                    )
                )
            else:
                findings.append(
                    Finding(
                        rule_name,
                        "drift",
                        f"{rel}: list {items} does NOT contain '{expected}'",
                        rel,
                    )
                )
        else:
            raise ValueError(f"unsupported regex mode: {mode}")
    return findings


def _parse_list_literal(raw: str) -> list[str]:
    """Parse a YAML flow-list body like `"3.11", "3.12"` into a list of strings."""
    items: list[str] = []
    for chunk in raw.split(","):
        cleaned = chunk.strip().strip('"').strip("'")
        if cleaned:
            items.append(cleaned)
    return items


def _check_yaml_pr_branches(
    rule_name: str,
    expected: str,
    file_path: Path,
) -> list[Finding]:
    """Verify `on.pull_request.branches` equals [expected] in a workflow YAML.

    Workflows that don't declare a `pull_request` trigger are silently skipped
    — the rule only fires on files that opt into the trigger at all.
    """
    findings: list[Finding] = []
    rel = str(file_path.relative_to(REPO_ROOT))
    try:
        with file_path.open("r", encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
    except (FileNotFoundError, yaml.YAMLError) as exc:
        return [Finding(rule_name, "warn", f"cannot parse {rel}: {exc}", rel)]

    # PyYAML parses the bare word `on:` as boolean True. Try both keys.
    triggers = doc.get("on") if isinstance(doc.get("on"), dict) else doc.get(True)
    if not isinstance(triggers, dict):
        return findings

    pr = triggers.get("pull_request")
    if not isinstance(pr, dict):
        return findings

    branches = pr.get("branches")
    if branches is None:
        # Legal — means "all branches". Flag as drift so it doesn't silently
        # widen the trigger surface.
        return [
            Finding(
                rule_name,
                "drift",
                f"{rel}: pull_request has no `branches` filter (expected ['{expected}'])",
                rel,
            )
        ]
    if isinstance(branches, str):
        branches = [branches]
    if not isinstance(branches, list):
        return [
            Finding(
                rule_name,
                "drift",
                f"{rel}: pull_request.branches is not a list: {branches!r}",
                rel,
            )
        ]

    if branches == [expected]:
        findings.append(
            Finding(rule_name, "ok", f"{rel}: pull_request.branches == ['{expected}']", rel)
        )
    else:
        findings.append(
            Finding(
                rule_name,
                "drift",
                f"{rel}: pull_request.branches == {branches} (expected ['{expected}'])",
                rel,
            )
        )
    return findings


def evaluate(rules: dict[str, Any]) -> list[RuleReport]:
    reports: list[RuleReport] = []
    for name, spec in rules.items():
        expected = str(spec["expected"])
        rule_mode = spec.get("mode", "exact")
        if rule_mode not in ALL_MODES:
            raise SystemExit(f"rule '{name}' uses unknown mode: {rule_mode}")

        report = RuleReport(rule=name, expected=expected)
        for check in spec.get("checks", []):
            check_mode = check.get("mode", rule_mode)
            files = _resolve_files(check)
            for file_path in files:
                if check_mode in _REGEX_MODES:
                    regex = check.get("regex") or spec.get("regex")
                    if not regex:
                        raise SystemExit(f"rule '{name}' missing regex")
                    report.findings.extend(
                        _check_regex(name, expected, check_mode, file_path, regex)
                    )
                elif check_mode == "yaml_pr_branches":
                    report.findings.extend(
                        _check_yaml_pr_branches(name, expected, file_path)
                    )
        reports.append(report)
    return reports


def _emit_text(reports: Iterable[RuleReport]) -> None:
    for report in reports:
        oks = [f for f in report.findings if f.status == "ok"]
        drifts = [f for f in report.findings if f.status == "drift"]
        warns = [f for f in report.findings if f.status == "warn"]

        if drifts:
            print(f"FAIL  {report.rule:32s}  DRIFT:")
            for f in drifts:
                print(f"    {f.detail}")
        elif warns:
            print(f"WARN  {report.rule:32s}  {len(warns)} warning(s):")
            for f in warns:
                print(f"    {f.detail}")
        elif oks:
            files = sorted({f.file for f in oks if f.file})
            print(
                f"OK    {report.rule:32s}  "
                f"({report.expected} across {len(files)} file(s))"
            )
        else:
            print(f"SKIP  {report.rule:32s}  (no matches; nothing to check)")


def _emit_json(reports: Iterable[RuleReport]) -> None:
    payload = {
        "rules": [
            {
                "rule": r.rule,
                "expected": r.expected,
                "failed": r.failed,
                "warned": r.warned,
                "findings": [f.to_dict() for f in r.findings],
            }
            for r in reports
        ]
    }
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--rules",
        type=Path,
        default=DEFAULT_RULES,
        help=f"Path to the ruleset YAML (default: {DEFAULT_RULES.relative_to(REPO_ROOT)}).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures (used in CI).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report instead of the text summary.",
    )
    args = parser.parse_args(argv)

    rules = _load_rules(args.rules)
    reports = evaluate(rules)

    if args.json:
        _emit_json(reports)
    else:
        _emit_text(reports)

    failed = any(r.failed for r in reports)
    warned = any(r.warned for r in reports)
    if failed or (args.strict and warned):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
