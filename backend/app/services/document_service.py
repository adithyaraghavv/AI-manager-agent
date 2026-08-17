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
from app.services.client_service import find_client, get_or_create_client, satisfied_document_types
from app.services import version_service
from app.storage.base import StorageBackend


class GatingBlocked(Exception):
    def __init__(self, decision: GatingDecision):
        self.decision = decision
        super().__init__(decision.reason)


class TemplateNotFound(Exception):
    pass


class TemplateFileMissing(Exception):
    """The database has a record for this template, but the actual file isn't
    on disk locally — happens on a fresh clone/environment that hasn't run
    the one-time template seed script yet (local files aren't part of git;
    the database is shared across every environment, but each one's local
    file storage is its own). Distinct from TemplateNotFound (no record at
    all) so the fix that's actually needed is obvious from the message."""
    def __init__(self, doc_type: str):
        self.doc_type = doc_type
        super().__init__(
            f"The '{doc_type}' template is on record but its file isn't set up on this "
            "environment yet. Run `python -m app.db.seed_templates` in the backend folder, "
            "then try again."
        )


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
    existing = satisfied_document_types(rest, client)

    decision = check_gate(config, phase.name, existing)
    if not decision.allowed:
        raise GatingBlocked(decision)

    template = rest.select_one("templates", doc_type=doc_type)
    if template is None:
        raise TemplateNotFound(doc_type)

    try:
        content = template_storage.get(template["storage_path"])
    except FileNotFoundError as e:
        raise TemplateFileMissing(doc_type) from e
    return TemplateResult(filename=template["filename"], content=content)


@dataclass
class UploadResult:
    stored_path: str
    filename: str
    phase_name: str
    version_number: int


def upload_document(
    rest: SupabaseRestClient,
    storage: StorageBackend,
    config: PhaseConfig,
    doc_type: str,
    client_name: str,
    content: bytes,
    extension: str,
    uploaded_by: str | None = None,
    comment: str | None = None,
) -> UploadResult:
    """Files a document for a client. Every call creates a new, permanent
    version in document_versions (see version_service) — re-uploading the
    same doc_type never overwrites or loses an earlier version; it only
    moves the "current" pointer in client_documents forward."""
    validate_upload(content, extension)
    phase = resolve_phase_for_document(config, doc_type)
    client = get_or_create_client(rest, storage, config, client_name)
    # Canonical stored casing, not whatever was typed this time — see
    # get_or_create_client's docstring for why this matters on a
    # case-sensitive filesystem.
    canonical_name = client["name"]
    existing = satisfied_document_types(rest, client)

    decision = check_gate(config, phase.name, existing)
    if not decision.allowed:
        raise GatingBlocked(decision)

    filename = build_filename(doc_type=doc_type, client_name=canonical_name, extension=extension)
    folder = f"{canonical_name}/{phase.sequence:02d}_{phase.name}"
    # Reserve the version number BEFORE saving, and fold it into the storage
    # path — build_filename's timestamp alone is only second-precision, so
    # two uploads in the same second would otherwise collide on disk and
    # silently overwrite each other despite getting distinct version rows.
    #
    # next_version_number reads-then-computes with no locking, so two
    # uploads landing at the same moment could both reserve the same
    # number — the DB's unique constraint catches that as a
    # VersionNumberConflict rather than silently duplicating a row; retry
    # with a freshly reserved number rather than surfacing that race to
    # the PM as a raw failure.
    version_number = stored_path = None
    for attempt in range(version_service.MAX_VERSION_CONFLICT_RETRIES):
        version_number = version_service.next_version_number(rest, client["id"], doc_type)
        stored_path = f"{folder}/v{version_number}_{filename}"
        storage.save(stored_path, content)
        try:
            version_service.record_version(
                rest, client["id"], doc_type, version_number, stored_path, filename,
                uploaded_by=uploaded_by, comment=comment,
            )
            break
        except version_service.VersionNumberConflict:
            if attempt == version_service.MAX_VERSION_CONFLICT_RETRIES - 1:
                raise
            continue

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

    return UploadResult(
        stored_path=stored_path, filename=filename, phase_name=phase.name, version_number=version_number
    )


def restore_document_version(
    rest: SupabaseRestClient,
    storage: StorageBackend,
    client_name: str,
    doc_type: str,
    version_number: int,
    uploaded_by: str | None = None,
    comment: str | None = None,
) -> UploadResult:
    """Makes an earlier version current again — WITHOUT destroying anything.
    This copies the old version's content forward as a brand new version
    (e.g. restoring v2 when v4 is current creates v5, a copy of v2's
    content); v2, v3, and v4 all still exist in the version history
    afterward. There is no code path in this app that deletes a version."""
    client = find_client(rest, client_name)
    if client is None:
        raise ClientDocumentNotFound(f"No client named {client_name!r}")

    try:
        old = version_service.get_version_content(rest, storage, client["id"], doc_type, version_number)
    except version_service.DocumentVersionNotFound as e:
        raise ClientDocumentNotFound(str(e)) from e

    record = rest.select_one("client_documents", client_id=client["id"], doc_type=doc_type)
    if record is None:
        raise ClientDocumentNotFound(f"No {doc_type!r} document on file for {client_name!r}")
    phase_name = record["phase_name"]

    extension = old.filename.rsplit(".", 1)[-1] if "." in old.filename else "bin"
    filename = build_filename(doc_type=doc_type, client_name=client["name"], extension=extension)
    new_version_number = version_service.next_version_number(rest, client["id"], doc_type)
    folder_prefix = record["storage_path"].rsplit("/", 1)[0]
    stored_path = f"{folder_prefix}/v{new_version_number}_{filename}"
    storage.save(stored_path, old.content)

    rest.update("client_documents", {"id": record["id"]}, {"storage_path": stored_path, "filename": filename})

    restore_comment = comment or f"Restored from version {version_number}"
    version_service.record_version(
        rest, client["id"], doc_type, new_version_number, stored_path, filename,
        uploaded_by=uploaded_by, comment=restore_comment,
    )

    return UploadResult(
        stored_path=stored_path, filename=filename, phase_name=phase_name, version_number=new_version_number
    )


class ClientDocumentNotFound(Exception):
    pass


def list_document_versions(rest: SupabaseRestClient, client_name: str, doc_type: str) -> list:
    """Every version on file for a client's document, oldest first. Returns
    an empty list (not an error) if the client exists but has never filed
    this doc_type — callers decide how to phrase "no versions yet."""
    client = find_client(rest, client_name)
    if client is None:
        raise ClientDocumentNotFound(f"No client named {client_name!r}")
    return version_service.list_versions(rest, client["id"], doc_type)


def get_document_version(
    rest: SupabaseRestClient, storage: StorageBackend, client_name: str, doc_type: str, version_number: int
):
    client = find_client(rest, client_name)
    if client is None:
        raise ClientDocumentNotFound(f"No client named {client_name!r}")
    try:
        return version_service.get_version_content(rest, storage, client["id"], doc_type, version_number)
    except version_service.DocumentVersionNotFound as e:
        raise ClientDocumentNotFound(str(e)) from e


@dataclass
class DocumentLocation:
    client_name: str
    doc_type: str
    folder_path: str
    filename: str


def get_document_location(rest: SupabaseRestClient, client_name: str, doc_type: str) -> DocumentLocation:
    """Where a filed document lives — a folder path, not the file itself.
    For a PM who just wants to know where something is (to browse it
    themselves later, e.g. once this is backed by a real SharePoint folder)
    rather than getting a direct download every time."""
    client = find_client(rest, client_name)
    if client is None:
        raise ClientDocumentNotFound(f"No client named {client_name!r}")

    record = rest.select_one("client_documents", client_id=client["id"], doc_type=doc_type)
    if record is None:
        raise ClientDocumentNotFound(f"No {doc_type!r} document on file for {client_name!r}")

    folder_path = record["storage_path"].rsplit("/", 1)[0]
    return DocumentLocation(
        client_name=client["name"], doc_type=doc_type, folder_path=folder_path, filename=record["filename"]
    )


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

    try:
        content = storage.get(record["storage_path"])
    except FileNotFoundError as e:
        raise ClientDocumentNotFound(
            f"{doc_type!r} is on record for {client_name!r}, but its file isn't present on this "
            "environment's local storage (the database is shared, local files aren't)."
        ) from e
    return TemplateResult(filename=record["filename"], content=content)
