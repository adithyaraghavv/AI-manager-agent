"""On-demand SOW metadata extraction — pulls contract value, start/end
dates, a scope summary, project team assignments, and document
responsibility (who owns/provides each document, and who approves it —
distinct roles, since SOWs differ on whether they split those or name one
party for both) out of a client's filed SOW so a PM can ask for them
directly instead of opening the document.

Re-runs from scratch on every call (no "is this stale" check) — the same
"never trust an earlier result" principle the chat assistant already
follows elsewhere in this app. The stored row is a cache of the last
extraction for anything that later wants to query it directly, not a
substitute for that.
"""

import json
from dataclasses import dataclass
from datetime import datetime

from openai import OpenAI

from app.config import settings
from app.core.text_extraction import extract_text
from app.db.rest_client import SupabaseRestClient
from app.services.client_service import find_client
from app.services.document_service import ClientDocumentNotFound, get_stored_document
from app.storage.base import StorageBackend

# Cap how much SOW text we send the model — long documents don't need their
# full body for four summary fields, and this keeps token usage bounded.
MAX_EXTRACTION_CHARS = 12000

EXTRACTION_SYSTEM_PROMPT = """You extract structured facts from a Statement of Work (SOW) document. \
Given the SOW's text, return a JSON object with exactly these keys: contract_value, start_date, \
end_date, scope_summary, team_assignments, document_responsibilities. Use null for any field the \
document doesn't actually state — never guess or invent a value, and never fill in a plausible-sounding \
name or role that isn't actually written in the text. contract_value and dates should be copied as \
written in the document (don't reformat or convert currency). scope_summary should be a few plain \
sentences describing what work is in scope, not a verbatim quote. team_assignments should be a JSON \
array of objects with "name" and "role" keys, for every person or role explicitly assigned to the \
project in the document (e.g. [{"name": "Jane Doe", "role": "Project Manager"}]) — null (not an empty \
array) if the SOW doesn't name a project team at all.

document_responsibilities should be a JSON object mapping a document name to an object with "owner" \
and "approver" keys — "owner" is whoever provides/authors/produces the document, "approver" is whoever \
reviews and signs off on it before it counts as done. SOWs vary: some name both roles separately for a \
document, some name only one party for both. Rules: (1) if the SOW clearly distinguishes who provides \
it from who approves it, put each in its own key; (2) if the SOW names only ONE party for a document \
with no distinction, put that same party in BOTH "owner" and "approver" — that's the only information \
available, not an invented distinction; (3) if the SOW says nothing at all about a document's \
responsibility, don't include that document as a key. Example: {"BRD": {"owner": "Client team", \
"approver": "Client team"}, "HLD": {"owner": "Marlabs team", "approver": "Client Sponsor"}}. Use null \
for document_responsibilities entirely if the SOW assigns responsibility for no documents at all."""


class SowExtractionFailed(Exception):
    pass


@dataclass
class SowMetadataResult:
    client_name: str
    contract_value: str | None
    start_date: str | None
    end_date: str | None
    scope_summary: str | None
    team_assignments: list | None
    document_responsibilities: dict | None
    extracted_at: str


@dataclass
class ApprovalReminderResult:
    found: bool
    client_name: str
    doc_type: str
    matched_doc_type: str | None = None
    owner: str | None = None
    approver: str | None = None
    reminder_message: str | None = None
    reason: str | None = None


def _match_document_responsibility(
    document_responsibilities: dict, requested_doc_type: str
) -> tuple[str, dict] | None:
    """Find the (matched_key, {"owner", "approver"}) entry for
    `requested_doc_type` in a document_responsibilities map. The PM's
    phrasing and the SOW's own wording for a document name rarely match
    exactly (e.g. "BRD" vs "Business Requirement Document (BRD)"), so this
    tries an exact case-insensitive match first, then a substring match in
    either direction, before giving up."""
    requested = requested_doc_type.strip().lower()
    if not requested:
        return None

    for key, entry in document_responsibilities.items():
        if key.strip().lower() == requested:
            return key, entry

    for key, entry in document_responsibilities.items():
        key_lower = key.strip().lower()
        if requested in key_lower or key_lower in requested:
            return key, entry

    return None


def _build_reminder_message(client_name: str, doc_type: str, approver: str) -> str:
    return (
        f"Subject: Approval Required for {doc_type} — {client_name}\n\n"
        f"Hi {approver},\n\n"
        f"The {doc_type} for {client_name} is currently awaiting your review/approval "
        f"per the SOW. Could you please take a look and confirm approval at your "
        f"earliest convenience so we can move this forward?\n\n"
        f"Thanks,\n"
    )


def _extract_fields_via_llm(text: str) -> dict:
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": text[:MAX_EXTRACTION_CHARS]},
        ],
    )
    return json.loads(response.choices[0].message.content)


def _persist(rest: SupabaseRestClient, client_id: int, fields: dict) -> dict:
    existing = rest.select_one("sow_metadata", client_id=client_id)
    payload = {
        "contract_value": fields.get("contract_value"),
        "start_date": fields.get("start_date"),
        "end_date": fields.get("end_date"),
        "scope_summary": fields.get("scope_summary"),
        "team_assignments": fields.get("team_assignments"),
        "document_responsibilities": fields.get("document_responsibilities"),
        "extracted_at": datetime.utcnow().isoformat(),
    }
    if existing is None:
        return rest.insert("sow_metadata", {"client_id": client_id, **payload})
    return rest.update("sow_metadata", {"id": existing["id"]}, payload)


def get_sow_summary(
    rest: SupabaseRestClient, storage: StorageBackend, client_name: str
) -> SowMetadataResult:
    client = find_client(rest, client_name)
    if client is None:
        raise SowExtractionFailed(f"No client named {client_name!r}")

    try:
        document = get_stored_document(rest, storage, client_name, "SOW")
    except ClientDocumentNotFound as e:
        raise SowExtractionFailed(
            f"No SOW is on file for {client['name']!r} yet."
        ) from e

    extension = document.filename.rsplit(".", 1)[-1] if "." in document.filename else ""
    text = extract_text(document.content, extension)
    if not text:
        raise SowExtractionFailed(
            f"Couldn't read text out of the SOW on file for {client['name']!r} — either its file type "
            f"('.{extension}') isn't supported for extraction, or it has no extractable text (e.g. a "
            "scanned image with no text layer)."
        )

    fields = _extract_fields_via_llm(text)
    row = _persist(rest, client["id"], fields)

    return SowMetadataResult(
        client_name=client["name"],
        contract_value=row.get("contract_value"),
        start_date=row.get("start_date"),
        end_date=row.get("end_date"),
        scope_summary=row.get("scope_summary"),
        team_assignments=row.get("team_assignments"),
        document_responsibilities=row.get("document_responsibilities"),
        extracted_at=row.get("extracted_at"),
    )


def generate_approval_reminder(
    rest: SupabaseRestClient, storage: StorageBackend, client_name: str, doc_type: str
) -> ApprovalReminderResult:
    """Who to chase for a document's APPROVAL specifically (not just who
    provides it), plus a ready-to-copy reminder addressed to them — built
    from the same document_responsibilities data get_sow_summary returns,
    re-extracted fresh (not a cached answer). Falls back to the document's
    owner only when the SOW names just one party for the document (no
    owner/approver distinction) — in that case owner and approver are
    already the same value, not a guess. Never drafts a reminder to an
    invented name — if the SOW doesn't say who approves this document, this
    returns found=False rather than guessing."""
    summary = get_sow_summary(rest, storage, client_name)

    if not summary.document_responsibilities:
        return ApprovalReminderResult(
            found=False,
            client_name=summary.client_name,
            doc_type=doc_type,
            reason=f"The SOW on file for {summary.client_name!r} doesn't assign responsibility for any documents.",
        )

    match = _match_document_responsibility(summary.document_responsibilities, doc_type)
    if match is None:
        return ApprovalReminderResult(
            found=False,
            client_name=summary.client_name,
            doc_type=doc_type,
            reason=(
                f"The SOW on file for {summary.client_name!r} doesn't say who's responsible for "
                f"{doc_type!r}."
            ),
        )

    matched_doc_type, entry = match
    owner = entry.get("owner") if isinstance(entry, dict) else entry
    approver = entry.get("approver") if isinstance(entry, dict) else entry
    if not approver:
        return ApprovalReminderResult(
            found=False,
            client_name=summary.client_name,
            doc_type=doc_type,
            matched_doc_type=matched_doc_type,
            reason=(
                f"The SOW on file for {summary.client_name!r} names who's responsible for "
                f"{matched_doc_type!r} but doesn't say who approves it."
            ),
        )

    return ApprovalReminderResult(
        found=True,
        client_name=summary.client_name,
        doc_type=doc_type,
        matched_doc_type=matched_doc_type,
        owner=owner,
        approver=approver,
        reminder_message=_build_reminder_message(
            summary.client_name, matched_doc_type, approver
        ),
    )
