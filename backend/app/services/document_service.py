"""Template retrieval and document upload — the two hard-gated operations.

Both functions enforce the gate deterministically (app.core.gating) before
touching storage. Callers (API routes, agent tools) must not bypass this by
calling storage directly.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.file_naming import build_filename
from app.core.gating import GatingDecision, check_gate, resolve_phase_for_document
from app.core.phase_config import PhaseConfig
from app.db.models import Client, ClientDocument, Template
from app.services.client_service import existing_document_types, get_or_create_client
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
    db: Session,
    client_storage: StorageBackend,
    template_storage: StorageBackend,
    config: PhaseConfig,
    doc_type: str,
    client_name: str,
) -> TemplateResult:
    phase = resolve_phase_for_document(config, doc_type)
    client = get_or_create_client(db, client_storage, config, client_name)
    existing = existing_document_types(db, client)

    decision = check_gate(config, phase.name, existing)
    if not decision.allowed:
        raise GatingBlocked(decision)

    template = db.query(Template).filter_by(doc_type=doc_type).one_or_none()
    if template is None:
        raise TemplateNotFound(doc_type)

    content = template_storage.get(template.storage_path)
    return TemplateResult(filename=template.filename, content=content)


@dataclass
class UploadResult:
    stored_path: str
    filename: str
    phase_name: str


def upload_document(
    db: Session,
    storage: StorageBackend,
    config: PhaseConfig,
    doc_type: str,
    client_name: str,
    content: bytes,
    extension: str,
) -> UploadResult:
    phase = resolve_phase_for_document(config, doc_type)
    client = get_or_create_client(db, storage, config, client_name)
    existing = existing_document_types(db, client)

    decision = check_gate(config, phase.name, existing)
    if not decision.allowed:
        raise GatingBlocked(decision)

    filename = build_filename(doc_type=doc_type, client_name=client_name, extension=extension)
    folder = f"{client_name}/{phase.sequence:02d}_{phase.name}"
    stored_path = f"{folder}/{filename}"
    storage.save(stored_path, content)

    record = db.query(ClientDocument).filter_by(client_id=client.id, doc_type=doc_type).one_or_none()
    if record is None:
        record = ClientDocument(
            client_id=client.id,
            phase_name=phase.name,
            doc_type=doc_type,
            storage_path=stored_path,
            filename=filename,
        )
        db.add(record)
    else:
        record.storage_path = stored_path
        record.filename = filename
    db.commit()

    return UploadResult(stored_path=stored_path, filename=filename, phase_name=phase.name)
