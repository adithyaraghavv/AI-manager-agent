"""On-demand plain-English summary of any filed document's actual content —
the generic counterpart to sow_extraction_service.get_sow_summary, which
only covers the SOW's fixed structured fields (contract value, dates,
team...). Every other document type doesn't share one common shape, so
this gives a prose overview instead of fixed fields.

Re-reads and re-summarizes from scratch on every call — same "never trust
a stale cached read" principle get_sow_summary already follows.
"""

from dataclasses import dataclass

from openai import OpenAI

from app.config import settings
from app.core.text_extraction import extract_text
from app.db.rest_client import SupabaseRestClient
from app.services import version_service
from app.services.client_service import find_client
from app.services.document_service import ClientDocumentNotFound, get_stored_document
from app.storage.base import StorageBackend

# Cap how much document text we send the model — a summary doesn't need the
# full body of a very long document, and this keeps token usage bounded.
MAX_SUMMARY_CHARS = 12000

SUMMARY_SYSTEM_PROMPT = """You summarize a project delivery document for a busy project manager who \
hasn't opened the file. Given the document's text, write a short plain-English overview — 3 to 6 \
sentences, or a few short bullet points if that reads more clearly — covering its purpose and the \
key points a PM would want to know at a glance. Base the summary strictly on the text given; never \
invent details, names, figures, or conclusions that aren't actually in the document."""


class DocumentSummaryFailed(Exception):
    pass


@dataclass
class DocumentSummaryResult:
    client_name: str
    doc_type: str
    filename: str
    summary: str
    version_number: int | None = None


def _summarize_via_llm(text: str) -> str:
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": text[:MAX_SUMMARY_CHARS]},
        ],
    )
    return response.choices[0].message.content.strip()


def summarize_document(
    rest: SupabaseRestClient,
    storage: StorageBackend,
    client_name: str,
    doc_type: str,
    version_number: int | None = None,
) -> DocumentSummaryResult:
    """Summarizes the CURRENT version on file by default. Pass `version_number`
    to summarize a specific past version instead — get_stored_document alone
    can only ever see the current pointer, so a PM asking for "version 2"
    while version 3 is current had no way to actually reach version 2's
    content; this is the fix for that."""
    client = find_client(rest, client_name)
    if client is None:
        raise DocumentSummaryFailed(f"No client named {client_name!r}")

    if version_number is None:
        try:
            document = get_stored_document(rest, storage, client_name, doc_type)
        except ClientDocumentNotFound as e:
            # get_stored_document already excludes a soft-deleted document (see
            # client_service.delete_client_document) — this reports the same
            # "not on file" reason a deleted document gets everywhere else,
            # rather than special-casing it.
            raise DocumentSummaryFailed(
                f"No {doc_type!r} document is on file for {client['name']!r} yet."
            ) from e
        resolved_version = None
    else:
        try:
            document = version_service.get_version_content(
                rest, storage, client["id"], doc_type, version_number
            )
        except version_service.DocumentVersionNotFound as e:
            # Keep the underlying reason from get_version_content (it already
            # distinguishes "no such version on record" from "the record
            # exists but its file is missing from storage" — e.g. deleted
            # directly in SharePoint outside the app) instead of collapsing
            # both into one generic "not on file" message, which was
            # actively misleading during testing.
            raise DocumentSummaryFailed(f"{e} (client: {client['name']!r})") from e
        resolved_version = version_number

    extension = document.filename.rsplit(".", 1)[-1] if "." in document.filename else ""
    text = extract_text(document.content, extension)
    if not text:
        raise DocumentSummaryFailed(
            f"Couldn't read text out of the {doc_type!r} on file for {client['name']!r} — either its "
            f"file type ('.{extension}') isn't supported for extraction, or it has no extractable text "
            "(e.g. a scanned image with no text layer)."
        )

    summary = _summarize_via_llm(text)
    return DocumentSummaryResult(
        client_name=client["name"],
        doc_type=doc_type,
        filename=document.filename,
        summary=summary,
        version_number=resolved_version,
    )
