"""Hard-block phase-gating logic.

Rule (per discovery doc, section 4): a document belonging to phase N cannot be
served (template request) or accepted (upload) until every required document
for ALL earlier phases (1 through N-1) already exists for that client — not
just the immediately preceding phase. This is a hard block, not a warning —
callers must refuse the action outright when `allowed` is False.

Pure functions only — no DB/storage/IO here, so this is trivially testable.
"""

from dataclasses import dataclass

from app.core.phase_config import Phase, PhaseConfig


@dataclass(frozen=True)
class GatingDecision:
    allowed: bool
    blocking_phase: str | None = None
    missing_documents: tuple[str, ...] = ()

    @property
    def reason(self) -> str | None:
        if self.allowed:
            return None
        docs = ", ".join(self.missing_documents)
        return f"Cannot proceed to phase '{self.blocking_phase}' until required documents are complete: {docs}"


def missing_documents(phase: Phase, existing_documents: set[str]) -> tuple[str, ...]:
    """Required documents for `phase` not present in `existing_documents`."""
    return tuple(
        doc for doc in phase.required_documents if doc not in existing_documents
    )


def check_gate(
    config: PhaseConfig, target_phase_name: str, existing_documents: set[str]
) -> GatingDecision:
    """Can a document belonging to `target_phase_name` be requested/uploaded?

    Walks every earlier phase in sequence order (1, 2, ... up to the one right
    before the target) and blocks on the first one that isn't fully complete.
    This means a gap in an early phase is always caught, even if a later
    phase happens to look complete — the whole hierarchy must be satisfied in
    order, not just the single phase immediately before the target.
    """
    target_phase = config.get(target_phase_name)
    earlier_phases = [p for p in config.phases if p.sequence < target_phase.sequence]

    for phase in earlier_phases:
        missing = missing_documents(phase, existing_documents)
        if missing:
            return GatingDecision(
                allowed=False, blocking_phase=phase.name, missing_documents=missing
            )

    return GatingDecision(allowed=True)


def resolve_phase_for_document(config: PhaseConfig, document_type: str) -> Phase:
    """Find which phase a given document type belongs to."""
    for phase in config.phases:
        if document_type in phase.required_documents:
            return phase
    raise ValueError(f"Document type {document_type!r} is not defined in any phase")
