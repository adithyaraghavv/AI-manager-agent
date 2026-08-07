"""Template retrieval and document upload — the two hard-gated operations.

Both functions enforce the gate deterministically (app.core.gating) before
touching storage. Callers (API routes, agent tools) must not bypass this by
calling storage directly.
"""
from dataclasses import dataclass

from app.core.file_naming import build_filename
from app.core.gating import GatingDecision, check_gate, resolve_phase_for_document
from app.core.phase_config import PhaseConfig
from app.core.upload_validation import InvalidUpload, validate_upload
from app.db.rest_client import SupabaseRestClient
from app.services.client_service import existing_document_types, find_client, get_or_create_client
from app.storage.base import StorageBackend


class GatingBlocked(Exception):
    def __init__(self, decision: GatingDecision):
        self.decision = decision
        super().__init__(decision.reason)


class TemplateNotFound(Exception):
    pass


@dataclass
class TemplateResult:
    filename: str
    content: bytes


def request_template(
    rest: SupabaseRestClient,
    client_storage: StorageBackend,
    template_storage: StorageBackend,
    config: PhaseConfig,
    doc_type: str,
    client_name: str,
) -> TemplateResult:
    phase = resolve_phase_for_document(config, doc_type)
    client = get_or_create_client(rest, client_storage, config, client_name)
    existing = existing_document_types(rest, client)

    decision = check_gate(config, phase.name, existing)
    if not decision.allowed:
        raise GatingBlocked(decision)

    template = rest.select_one("templates", doc_type=doc_type)
    if template is None:
        raise TemplateNotFound(doc_type)

    content = template_storage.get(template["storage_path"])
    return TemplateResult(filename=template["filename"], content=content)


@dataclass
class UploadResult:
    stored_path: str
    filename: str
    phase_name: str


def upload_document(
    rest: SupabaseRestClient,
    storage: StorageBackend,
    config: PhaseConfig,
    doc_type: str,
    client_name: str,
    content: bytes,
    extension: str,
) -> UploadResult:
    validate_upload(content, extension)
    phase = resolve_phase_for_document(config, doc_type)
    client = get_or_create_client(rest, storage, config, client_name)
    # Canonical stored casing, not whatever was typed this time — see
    # get_or_create_client's docstring for why this matters on a
    # case-sensitive filesystem.
    canonical_name = client["name"]
    existing = existing_document_types(rest, client)

    decision = check_gate(config, phase.name, existing)
    if not decision.allowed:
        raise GatingBlocked(decision)

    filename = build_filename(doc_type=doc_type, client_name=canonical_name, extension=extension)
    folder = f"{canonical_name}/{phase.sequence:02d}_{phase.name}"
    stored_path = f"{folder}/{filename}"
    storage.save(stored_path, content)

    record = rest.select_one("client_documents", client_id=client["id"], doc_type=doc_type)
    if record is None:
        rest.insert(
            "client_documents",
            {
                "client_id": client["id"],
                "phase_name": phase.name,
                "doc_type": doc_type,
                "storage_path": stored_path,
                "filename": filename,
            },
        )
    else:
        rest.update(
            "client_documents",
            {"id": record["id"]},
            {"storage_path": stored_path, "filename": filename},
        )

    return UploadResult(stored_path=stored_path, filename=filename, phase_name=phase.name)


class ClientDocumentNotFound(Exception):
    pass


def get_stored_document(
    rest: SupabaseRestClient,
    storage: StorageBackend,
    client_name: str,
    doc_type: str,
) -> TemplateResult:
    """Fetch an already-uploaded document for a client — not gated, since the
    document already exists (gating only governs whether a NEW one can be
    requested/filed). Used by search results and any other "get me the file
    that's already on record" path."""
    client = find_client(rest, client_name)
    if client is None:
        raise ClientDocumentNotFound(f"No client named {client_name!r}")

    record = rest.select_one("client_documents", client_id=client["id"], doc_type=doc_type)
    if record is None:
        raise ClientDocumentNotFound(f"No {doc_type!r} document on file for {client_name!r}")

    content = storage.get(record["storage_path"])
    return TemplateResult(filename=record["filename"], content=content)
