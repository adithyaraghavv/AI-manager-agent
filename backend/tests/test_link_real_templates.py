import pytest

from app.core.phase_config import Phase, PhaseConfig
from app.db.link_real_templates import (
    find_match,
    link_real_templates,
    real_template_folder,
)
from app.storage.local import LocalFilesystemStorage

CONFIG = PhaseConfig(
    [
        Phase(
            name="Pre-requisites",
            sequence=1,
            required_documents=("MSA", "SOW", "Kick-off Deck"),
        ),
        Phase(
            name="Requirement Analysis",
            sequence=2,
            required_documents=("Business Requirement Document (BRD)",),
        ),
    ]
)


@pytest.fixture
def storage(tmp_path):
    return LocalFilesystemStorage(tmp_path)


def test_real_template_folder_uses_dot_naming_not_zero_padded_underscore():
    # Tarun's real folders are "1. Pre-requisites", not the app's own mock
    # folders ("01_Pre-requisites") — this is the exact naming mismatch that
    # caused the app to never see his real files in the first place.
    phase = CONFIG.get("Pre-requisites")
    assert real_template_folder(phase) == "1. Pre-requisites"


def test_find_match_matches_despite_underscore_vs_space_and_case():
    files = ["1. Pre-requisites/Kick-off_Deck.docx", "1. Pre-requisites/MSA.docx"]
    assert find_match("Kick-off Deck", files) == "1. Pre-requisites/Kick-off_Deck.docx"


def test_find_match_matches_after_dropping_approved_qualifier():
    # Real files often drop qualifier words the doc_type keeps — a doc_type
    # of "Approved HLD" should still match a file renamed to just "HLD.docx".
    files = ["4. Implementation (Coding)/HLD.docx"]
    assert find_match("Approved HLD", files) == "4. Implementation (Coding)/HLD.docx"


def test_find_match_matches_acronym_in_parentheses():
    files = ["2. Requirement Analysis/BRD.docx"]
    assert (
        find_match("Business Requirement Document (BRD)", files)
        == "2. Requirement Analysis/BRD.docx"
    )


def test_find_match_returns_none_when_ambiguous():
    # Two files both normalize to the same name ("Sow" vs "SOW") — refuse to
    # guess which one is the real template rather than picking one silently.
    files = ["1. Pre-requisites/SOW.docx", "1. Pre-requisites/Sow.docx"]
    assert find_match("SOW", files) is None


def test_find_match_returns_none_when_no_file_matches():
    files = ["1. Pre-requisites/MSA.docx"]
    assert find_match("SOW", files) is None


def test_link_real_templates_dry_run_does_not_write_to_db(rest, storage):
    storage.save("1. Pre-requisites/MSA.docx", b"real msa content")
    storage.save("1. Pre-requisites/SOW.docx", b"real sow content")
    storage.save("1. Pre-requisites/Kick-off_Deck.docx", b"real deck content")

    link_real_templates(rest, storage, CONFIG, apply=False)

    assert rest.select("templates") == []


def test_link_real_templates_apply_links_matched_doc_types_only(rest, storage):
    storage.save("1. Pre-requisites/MSA.docx", b"real msa content")
    storage.save("1. Pre-requisites/SOW.docx", b"real sow content")
    # Kick-off Deck's real file intentionally missing — should stay unmatched.
    storage.save(
        "2. Requirement Analysis/BRD.docx", b"real brd content"
    )

    link_real_templates(rest, storage, CONFIG, apply=True)

    msa = rest.select_one("templates", doc_type="MSA")
    assert msa["storage_path"] == "1. Pre-requisites/MSA.docx"
    assert msa["filename"] == "MSA.docx"

    brd = rest.select_one("templates", doc_type="Business Requirement Document (BRD)")
    assert brd["storage_path"] == "2. Requirement Analysis/BRD.docx"

    assert rest.select_one("templates", doc_type="Kick-off Deck") is None


def test_link_real_templates_apply_overwrites_an_existing_mock_row(rest, storage):
    rest.insert(
        "templates",
        {
            "doc_type": "MSA",
            "storage_path": "01_Pre-requisites/msa.txt",
            "filename": "msa.txt",
        },
    )
    storage.save("1. Pre-requisites/MSA.docx", b"real msa content")

    link_real_templates(rest, storage, CONFIG, apply=True)

    rows = rest.select("templates", doc_type="MSA")
    assert len(rows) == 1  # updated in place, not duplicated
    assert rows[0]["storage_path"] == "1. Pre-requisites/MSA.docx"
