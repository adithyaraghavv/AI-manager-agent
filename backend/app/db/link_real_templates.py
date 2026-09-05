"""Points the `templates` table at the REAL template files Tarun uploaded
directly to SharePoint, instead of the MOCK placeholder files seed_templates.py
created (see that module's docstring — it only ever had 3 real files built in,
everything else got a fake .txt).

Tarun's real files live in a separate, differently-named set of folders in
the same SharePoint library — "1. Pre-requisites", "2. Requirement Analysis",
... (no zero-padding, ". " separator) — versus the app's own
"01_Pre-requisites" folders (zero-padded, "_" separator) that hold the mock
files. The app never knew Tarun's folder existed, so it kept serving the mock
one even after his real files were uploaded.

This script does NOT move or copy any file in SharePoint. It only repoints
each doc_type's `templates.storage_path` at Tarun's real file, matched by
name. Run with --dry-run first (the default) to see the proposed matches
before writing anything; pass --apply to actually update the DB.

Usage (from backend/):
    uv run python -m app.db.link_real_templates            # dry run, just prints
    uv run python -m app.db.link_real_templates --apply     # actually updates the DB
"""

import argparse
import re

from app.config import settings
from app.core.phase_config import Phase, PhaseConfig, get_phase_config
from app.db.rest_client import SupabaseRestClient
from app.deps import get_template_storage
from app.storage.base import StorageBackend

_PAREN_RE = re.compile(r"\(([^)]+)\)")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
# Qualifier words a doc_type keeps ("Approved HLD") that a real file's name
# often drops ("HLD.docx") — stripped out as its own match candidate below.
_QUALIFIER_WORD_RE = re.compile(r"(?i)\bapproved\b")


def _normalize(text: str) -> str:
    """Lowercase, punctuation/underscores/hyphens collapsed to nothing, so
    'Kick-off_Deck.docx' and 'Kick-off Deck' compare equal, and 'BRD.docx'
    can be matched against an acronym pulled out of a longer doc_type."""
    return _NON_ALNUM_RE.sub("", text.lower())


def _candidate_names(doc_type: str) -> set[str]:
    """Every reasonable normalized name a real file might be saved under for
    this doc_type: the full name; if the doc_type has a parenthesized
    acronym like 'Business Requirement Document (BRD)', the acronym alone
    and the name with the parenthetical stripped, since a real file is just
    as likely to be named 'BRD.docx' as the full spelled-out name; and the
    doc_type with a qualifier word like "Approved" removed, since a file is
    often just named 'HLD.docx' for a doc_type of 'Approved HLD'."""
    candidates = {_normalize(doc_type)}
    for acronym in _PAREN_RE.findall(doc_type):
        candidates.add(_normalize(acronym))
    without_parens = _PAREN_RE.sub("", doc_type).strip()
    if without_parens:
        candidates.add(_normalize(without_parens))
    without_qualifier = _QUALIFIER_WORD_RE.sub("", doc_type).strip()
    without_qualifier = re.sub(r"\s+", " ", without_qualifier)
    if without_qualifier:
        candidates.add(_normalize(without_qualifier))
    return candidates


def real_template_folder(phase: Phase) -> str:
    """Tarun's real-template folder naming convention: no zero-padding on
    the sequence number, ". " between the number and the phase name — as
    opposed to the app's own "NN_Phase Name" folders for its mock files."""
    return f"{phase.sequence}. {phase.name}"


def find_match(doc_type: str, files: list[str]) -> str | None:
    """`files` are paths as returned by StorageBackend.list() (one folder's
    direct children). Returns the single matching file's path, or None if
    zero or more than one file's name matches this doc_type — an ambiguous
    match is treated the same as no match, since guessing wrong here means
    a PM silently gets the wrong template."""
    candidates = _candidate_names(doc_type)
    matches = []
    for path in files:
        filename = path.rsplit("/", 1)[-1]
        stem = filename.rsplit(".", 1)[0]
        if _normalize(stem) in candidates:
            matches.append(path)
    if len(matches) == 1:
        return matches[0]
    return None


def link_real_templates(
    rest: SupabaseRestClient,
    storage: StorageBackend,
    config: PhaseConfig,
    apply: bool,
) -> None:
    linked, unmatched = [], []

    for phase in config.phases:
        folder = real_template_folder(phase)
        files = storage.list(folder)
        if not files:
            for doc_type in phase.required_documents:
                unmatched.append((phase.name, doc_type, "folder not found or empty"))
            continue

        for doc_type in phase.required_documents:
            match = find_match(doc_type, files)
            if match is None:
                unmatched.append((phase.name, doc_type, "no unambiguous filename match"))
                continue

            filename = match.rsplit("/", 1)[-1]
            linked.append((phase.name, doc_type, match))

            if apply:
                existing = rest.select_one("templates", doc_type=doc_type)
                if existing is None:
                    rest.insert(
                        "templates",
                        {"doc_type": doc_type, "storage_path": match, "filename": filename},
                    )
                else:
                    rest.update(
                        "templates",
                        {"id": existing["id"]},
                        {"storage_path": match, "filename": filename},
                    )

    print(f"{'Linked' if apply else 'Would link'} {len(linked)} real template(s):")
    for phase_name, doc_type, path in linked:
        print(f"  [{phase_name}] {doc_type} -> {path}")

    if unmatched:
        print(f"\n{len(unmatched)} document type(s) NOT matched (left untouched):")
        for phase_name, doc_type, reason in unmatched:
            print(f"  [{phase_name}] {doc_type} — {reason}")

    if not apply and linked:
        print("\nDry run only — re-run with --apply to actually update the database.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually update the templates table (default: dry run, just prints matches).",
    )
    args = parser.parse_args()

    rest = SupabaseRestClient(settings.supabase_url, settings.supabase_key)
    storage = get_template_storage()
    try:
        link_real_templates(rest, storage, get_phase_config(), apply=args.apply)
    finally:
        rest.close()


if __name__ == "__main__":
    main()
