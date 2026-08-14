"""On-demand SOW metadata extraction — pulls contract value, start/end
dates, a scope summary, project team assignments, and document ownership
(who's responsible for providing each document type) out of a client's
filed SOW so a PM can ask for them directly instead of opening the
document.

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
array) if the SOW doesn't name a project team at all. document_responsibilities should be a JSON object \
mapping a document name to who's responsible for providing it, exactly as stated in the SOW (e.g. \
{"BRD": "Client team", "HLD": "Marlabs team"}) — null if the SOW doesn't assign responsibility for any \
documents. Only include entries you can point to actual text for."""


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


def get_sow_summary(rest: SupabaseRestClient, storage: StorageBackend, client_name: str) -> SowMetadataResult:
    client = find_client(rest, client_name)
    if client is None:
        raise SowExtractionFailed(f"No client named {client_name!r}")

    try:
        document = get_stored_document(rest, storage, client_name, "SOW")
    except ClientDocumentNotFound as e:
        raise SowExtractionFailed(f"No SOW is on file for {client['name']!r} yet.") from e

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
