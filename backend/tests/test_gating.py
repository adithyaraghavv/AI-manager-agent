import pytest

from app.core.gating import check_gate, missing_documents, resolve_phase_for_document
from app.core.phase_config import Phase, PhaseConfig

CONFIG = PhaseConfig(
    [
        Phase(
            name="Pre-requisites",
            sequence=1,
            required_documents=("MSA", "SOW", "Pricing"),
        ),
        Phase(name="Requirement Analysis", sequence=2, required_documents=("BRD",)),
        Phase(name="System Design", sequence=3, required_documents=("SRS",)),
    ]
)


def test_phase_1_always_allowed_regardless_of_existing_docs():
    decision = check_gate(CONFIG, "Pre-requisites", existing_documents=set())
    assert decision.allowed


def test_phase_2_blocked_when_phase_1_incomplete():
    decision = check_gate(CONFIG, "Requirement Analysis", existing_documents={"MSA"})
    assert not decision.allowed
    assert decision.blocking_phase == "Pre-requisites"
    assert set(decision.missing_documents) == {"SOW", "Pricing"}


def test_phase_2_allowed_when_phase_1_complete():
    decision = check_gate(
        CONFIG, "Requirement Analysis", existing_documents={"MSA", "SOW", "Pricing"}
    )
    assert decision.allowed


def test_phase_3_blocked_on_earliest_incomplete_phase_not_just_immediate_previous():
    # Phase 2 (immediate previous) is complete, but phase 1 is not -> must still block,
    # and block on phase 1 specifically since that's the earliest gap in the hierarchy.
    decision = check_gate(CONFIG, "System Design", existing_documents={"BRD"})
    assert not decision.allowed
    assert decision.blocking_phase == "Pre-requisites"
    assert set(decision.missing_documents) == {"MSA", "SOW", "Pricing"}


def test_phase_3_allowed_only_when_both_earlier_phases_complete():
    decision = check_gate(
        CONFIG, "System Design", existing_documents={"MSA", "SOW", "Pricing", "BRD"}
    )
    assert decision.allowed


def test_missing_documents_returns_only_absent_ones():
    phase = CONFIG.get("Pre-requisites")
    missing = missing_documents(phase, {"MSA"})
    assert set(missing) == {"SOW", "Pricing"}


def test_resolve_phase_for_document():
    assert resolve_phase_for_document(CONFIG, "BRD").name == "Requirement Analysis"


def test_resolve_phase_for_unknown_document_raises():
    with pytest.raises(ValueError):
        resolve_phase_for_document(CONFIG, "NotADoc")


def test_unknown_phase_raises():
    with pytest.raises(ValueError):
        check_gate(CONFIG, "Nonexistent Phase", existing_documents=set())


def test_noncontiguous_sequence_rejected():
    with pytest.raises(ValueError):
        PhaseConfig(
            [
                Phase(name="A", sequence=1, required_documents=()),
                Phase(name="B", sequence=3, required_documents=()),
            ]
        )
