from app.core.document_lookup import find_document_types
from app.core.phase_config import Phase, PhaseConfig

CONFIG = PhaseConfig(
    [
        Phase(name="Pre-requisites", sequence=1, required_documents=("MSA", "SOW", "Pricing")),
        Phase(
            name="Testing (STLC Integrated)",
            sequence=2,
            required_documents=("Approved Test Plan", "Test Environment Ready", "Test Data Prepared"),
        ),
        Phase(
            name="Deployment",
            sequence=3,
            required_documents=("Signed-off Test Summary Report", "Release Notes"),
        ),
    ]
)


def test_ambiguous_query_returns_every_matching_document_type():
    # The exact real-world case this exists for: "test" alone is genuinely
    # ambiguous between four different document types across two phases.
    matches = find_document_types(CONFIG, "test")
    doc_types = {m.doc_type for m in matches}
    assert doc_types == {
        "Approved Test Plan",
        "Test Environment Ready",
        "Test Data Prepared",
        "Signed-off Test Summary Report",
    }


def test_unambiguous_query_returns_single_match():
    matches = find_document_types(CONFIG, "SOW")
    assert len(matches) == 1
    assert matches[0].doc_type == "SOW"
    assert matches[0].phase_name == "Pre-requisites"


def test_match_is_case_insensitive():
    matches = find_document_types(CONFIG, "sow")
    assert len(matches) == 1
    assert matches[0].doc_type == "SOW"


def test_no_match_returns_empty_list_not_an_error():
    assert find_document_types(CONFIG, "nonexistent document") == []


def test_blank_query_returns_empty_list():
    assert find_document_types(CONFIG, "   ") == []


def test_match_includes_phase_name_for_each_result():
    matches = find_document_types(CONFIG, "release")
    assert len(matches) == 1
    assert matches[0].phase_name == "Deployment"
