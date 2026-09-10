"""Document version history: every upload for a (client, doc_type) creates a
new, immutable row in document_versions instead of overwriting the last one.
client_documents (see client_service.py) always points at the current
version — this module is the only thing that reads/writes the full history.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.db.rest_client import SupabaseRestClient
from app.storage.base import StorageBackend

# A real, visible top-level folder in the same storage backend — a deleted
# version's file is physically moved here, not just hidden by a DB flag, so
# it's genuinely gone from the client's folder (as opposed to
# client_service.delete_client_document/delete_client, which only ever hide
# a DB row and never touch the real file). The client/phase folder structure
# underneath mirrors the original path automatically, since it's just that
# same path with this prefix — nothing pre-created, it only appears once
# something's actually deleted into it.
RECYCLE_BIN_ROOT = "Recycle Bin"


def _recycle_bin_path(storage_path: str) -> str:
    return f"{RECYCLE_BIN_ROOT}/{storage_path}"

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
    deleted_at: str | None = None
    # Only set by document_service.list_document_versions (the PM-facing
    # display path) — True when this version's database row exists but its
    # file no longer exists in storage, e.g. someone deleted it directly in
    # SharePoint outside the app. list_versions itself never sets this; it's
    # a pure DB read and doesn't touch storage.
    file_missing: bool = False


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
        deleted_at=row.get("deleted_at"),
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
    """Every version on file for this client + doc type, oldest first —
    including deleted ones (with deleted_at set), so a PM asking about a
    document's history still sees that a version was deleted and when,
    rather than it silently disappearing from the list."""
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
            deleted_at=r.get("deleted_at"),
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
    if row is None or row.get("deleted_at"):
        raise DocumentVersionNotFound(
            f"No version {version_number} of {doc_type!r} on record."
        )

    try:
        content = storage.get(row["storage_path"])
    except FileNotFoundError as e:
        raise DocumentVersionNotFound(
            f"Version {version_number} of {doc_type!r} is on record but its file is missing from "
            "storage — it may have been deleted or moved outside the app."
        ) from e
    return VersionContent(
        filename=row["filename"], content=content, version_number=version_number
    )


def delete_version(
    rest: SupabaseRestClient,
    storage: StorageBackend,
    recycle_storage: StorageBackend,
    client_id: int,
    doc_type: str,
    version_number: int,
) -> VersionInfo:
    """Moves a specific version's real file into the Recycle Bin folder (see
    RECYCLE_BIN_ROOT) and marks it deleted. Unlike client_service's
    delete_client_document (which only ever hides a DB row), this actually
    removes the file from its visible client/phase folder — restore_version
    moves it back exactly as it was.

    `recycle_storage` is a DIFFERENT StorageBackend instance than `storage`
    — rooted one level higher (see deps.get_recycle_bin_storage), so
    "Recycle Bin" lands as a sibling of the Clients/Templates folders rather
    than nested inside them. `storage` is only ever used for the original
    client-scoped path."""
    row = rest.select_one(
        "document_versions", client_id=client_id, doc_type=doc_type, version_number=version_number
    )
    if row is None:
        raise DocumentVersionNotFound(
            f"No version {version_number} on file for doc type {doc_type!r}"
        )
    if row.get("deleted_at"):
        raise DocumentVersionNotFound(
            f"Version {version_number} of {doc_type!r} is already deleted"
        )

    try:
        content = storage.get(row["storage_path"])
        recycle_storage.save(_recycle_bin_path(row["storage_path"]), content)
        storage.delete(row["storage_path"])
    except FileNotFoundError:
        # Record exists but the file's already gone from storage somehow —
        # still mark it deleted rather than leaving the DB out of sync with
        # a file that isn't there to move.
        pass

    updated = rest.update(
        "document_versions",
        {"id": row["id"]},
        {"deleted_at": datetime.now(timezone.utc).isoformat()},
    )
    return VersionInfo(
        version_number=updated["version_number"],
        filename=updated["filename"],
        storage_path=updated["storage_path"],
        uploaded_by=updated.get("uploaded_by"),
        comment=updated.get("comment"),
        uploaded_at=updated.get("uploaded_at"),
        deleted_at=updated.get("deleted_at"),
    )


def restore_version(
    rest: SupabaseRestClient,
    storage: StorageBackend,
    recycle_storage: StorageBackend,
    client_id: int,
    doc_type: str,
    version_number: int,
) -> VersionInfo:
    """Reverses delete_version: moves the file back out of the Recycle Bin
    to its original path and clears deleted_at. See delete_version's
    docstring for why `recycle_storage` is a separate instance from
    `storage`."""
    row = rest.select_one(
        "document_versions", client_id=client_id, doc_type=doc_type, version_number=version_number
    )
    if row is None or not row.get("deleted_at"):
        raise DocumentVersionNotFound(
            f"No deleted version {version_number} of {doc_type!r} found to restore"
        )

    try:
        content = recycle_storage.get(_recycle_bin_path(row["storage_path"]))
        storage.save(row["storage_path"], content)
        recycle_storage.delete(_recycle_bin_path(row["storage_path"]))
    except FileNotFoundError:
        # The file isn't in the Recycle Bin either (e.g. manually removed
        # there) — still clear deleted_at rather than leaving the PM stuck
        # unable to restore a record that has nothing left to move.
        pass

    updated = rest.update("document_versions", {"id": row["id"]}, {"deleted_at": None})
    return VersionInfo(
        version_number=updated["version_number"],
        filename=updated["filename"],
        storage_path=updated["storage_path"],
        uploaded_by=updated.get("uploaded_by"),
        comment=updated.get("comment"),
        uploaded_at=updated.get("uploaded_at"),
        deleted_at=updated.get("deleted_at"),
    )
