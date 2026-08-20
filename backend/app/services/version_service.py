"""Document version history: every upload for a (client, doc_type) creates a
new, immutable row in document_versions instead of overwriting the last one.
client_documents (see client_service.py) always points at the current
version — this module is the only thing that reads/writes the full history.
"""

from dataclasses import dataclass

import httpx

from app.db.rest_client import SupabaseRestClient
from app.storage.base import StorageBackend

# next_version_number() reads-then-computes with no locking, so two uploads
# for the exact same (client, doc_type) landing at the same moment could both
# reserve the same number. The DB's unique constraint (client_id, doc_type,
# version_number) catches that as a conflict rather than silently duplicating
# — document_service.upload_document retries this many times with a freshly
# reserved number before giving up.
MAX_VERSION_CONFLICT_RETRIES = 3


class DocumentVersionNotFound(Exception):
    pass


class VersionNumberConflict(Exception):
    """Raised when two uploads raced for the same version number — the
    caller should retry with a freshly reserved number, not surface this
    as-is to the PM."""


@dataclass
class VersionInfo:
    version_number: int
    filename: str
    storage_path: str
    uploaded_by: str | None
    comment: str | None
    uploaded_at: str | None


@dataclass
class VersionContent:
    filename: str
    content: bytes
    version_number: int


def next_version_number(rest: SupabaseRestClient, client_id: int, doc_type: str) -> int:
    """The version number the NEXT upload for this (client, doc_type) will
    get. Callers must use this to build a storage path BEFORE saving the
    file — see document_service.upload_document — so the on-disk path is
    unique even if two uploads land in the same second (build_filename's
    timestamp alone is not fine-grained enough to guarantee that)."""
    existing = rest.select("document_versions", client_id=client_id, doc_type=doc_type)
    if not existing:
        return 1
    return max(row["version_number"] for row in existing) + 1


def record_version(
    rest: SupabaseRestClient,
    client_id: int,
    doc_type: str,
    version_number: int,
    storage_path: str,
    filename: str,
    uploaded_by: str | None = None,
    comment: str | None = None,
) -> VersionInfo:
    """Records a version whose number was already reserved via
    next_version_number and whose file is already saved. Never overwrites
    or removes an earlier version.

    Raises VersionNumberConflict (not the raw HTTP error) if another upload
    already claimed this exact version_number in the moment between this
    call and next_version_number reserving it — the DB's unique constraint
    is the actual source of truth here, this is just surfacing that as a
    typed exception the caller can retry on."""
    try:
        row = _insert_version_row(
            rest,
            client_id,
            doc_type,
            version_number,
            storage_path,
            filename,
            uploaded_by,
            comment,
        )
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 409:
            raise VersionNumberConflict(
                f"Version {version_number} of {doc_type!r} was already claimed by a concurrent upload."
            ) from e
        raise
    return VersionInfo(
        version_number=row["version_number"],
        filename=row["filename"],
        storage_path=row["storage_path"],
        uploaded_by=row.get("uploaded_by"),
        comment=row.get("comment"),
        uploaded_at=row.get("uploaded_at"),
    )


def _insert_version_row(
    rest: SupabaseRestClient,
    client_id: int,
    doc_type: str,
    version_number: int,
    storage_path: str,
    filename: str,
    uploaded_by: str | None,
    comment: str | None,
) -> dict:
    return rest.insert(
        "document_versions",
        {
            "client_id": client_id,
            "doc_type": doc_type,
            "version_number": version_number,
            "storage_path": storage_path,
            "filename": filename,
            "uploaded_by": uploaded_by,
            "comment": comment,
        },
    )


def list_versions(
    rest: SupabaseRestClient, client_id: int, doc_type: str
) -> list[VersionInfo]:
    """Every version on file for this client + doc type, oldest first."""
    rows = rest.select("document_versions", client_id=client_id, doc_type=doc_type)
    rows.sort(key=lambda r: r["version_number"])
    return [
        VersionInfo(
            version_number=r["version_number"],
            filename=r["filename"],
            storage_path=r["storage_path"],
            uploaded_by=r.get("uploaded_by"),
            comment=r.get("comment"),
            uploaded_at=r.get("uploaded_at"),
        )
        for r in rows
    ]


def get_version_content(
    rest: SupabaseRestClient,
    storage: StorageBackend,
    client_id: int,
    doc_type: str,
    version_number: int,
) -> VersionContent:
    row = rest.select_one(
        "document_versions",
        client_id=client_id,
        doc_type=doc_type,
        version_number=version_number,
    )
    if row is None:
        raise DocumentVersionNotFound(
            f"No version {version_number} on file for doc type {doc_type!r}"
        )

    try:
        content = storage.get(row["storage_path"])
    except FileNotFoundError as e:
        raise DocumentVersionNotFound(
            f"Version {version_number} of {doc_type!r} is on record but its file isn't present on this "
            "environment's local storage."
        ) from e
    return VersionContent(
        filename=row["filename"], content=content, version_number=version_number
    )
