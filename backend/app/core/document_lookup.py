"""Fuzzy document-type lookup for the conversational agent.

request_template (see app.services.document_service) needs an EXACT
document-type string — that's correct and intentional, it's what makes
gating deterministic. But a PM asking in plain English often doesn't know
the exact spelling ("the test document", "the SOW") and shouldn't have to.
This module bridges the two: given a loose phrase, it returns every real
document type that could plausibly match, so the agent can either proceed
directly (one match) or ask a clarifying question (multiple matches)
instead of guessing at request_template.
"""
from dataclasses import dataclass

from app.core.phase_config import PhaseConfig


@dataclass
class DocumentTypeMatch:
    doc_type: str
    phase_name: str


def find_document_types(config: PhaseConfig, query: str) -> list[DocumentTypeMatch]:
    """Every known document type whose name contains `query` (case-insensitive,
    substring match on either side — 'test' matches 'Approved Test Plan' and
    'sow' matches 'SOW'). Returns an empty list, never raises, if nothing
    matches — the caller decides how to phrase that to the PM."""
    q = query.strip().lower()
    if not q:
        return []

    matches = []
    for phase in config.phases:
        for doc_type in phase.required_documents:
            if q in doc_type.lower():
                matches.append(DocumentTypeMatch(doc_type=doc_type, phase_name=phase.name))
    return matches
