from unittest.mock import patch

import pytest

from app.core.phase_config import Phase, PhaseConfig
from app.services.document_service import (
    ClientDocumentNotFound,
    get_document_version,
    list_document_versions,
    restore_document_version,
    upload_document,
)
from app.services import version_service
from app.services.version_service import (
    VersionNumberConflict,
    get_version_content,
    list_versions,
)
from app.storage.local import LocalFilesystemStorage

CONFIG = PhaseConfig(
    [
        Phase(name="Pre-requisites", sequence=1, required_documents=("MSA",)),
    ]
)


@pytest.fixture
def storage(tmp_path):
    return LocalFilesystemStorage(tmp_path)


def test_reuploading_same_doc_type_creates_new_version_not_overwrite(rest, storage):
    upload_document(
        rest, storage, CONFIG, "MSA", "Acme", b"v1 content", "pdf", uploaded_by="Priya"
    )
    upload_document(
        rest, storage, CONFIG, "MSA", "Acme", b"v2 content", "pdf", uploaded_by="Priya"
    )
    upload_document(
        rest, storage, CONFIG, "MSA", "Acme", b"v3 content", "pdf", uploaded_by="Priya"
    )

    client = rest.select_one("clients", name="Acme")
    versions = list_versions(rest, client["id"], "MSA")

    assert [v.version_number for v in versions] == [1, 2, 3]
    # Every version's actual file content is still recoverable, not just the latest.
    assert (
        get_version_content(rest, storage, client["id"], "MSA", 1).content
        == b"v1 content"
    )
    assert (
        get_version_content(rest, storage, client["id"], "MSA", 2).content
        == b"v2 content"
    )
    assert (
        get_version_content(rest, storage, client["id"], "MSA", 3).content
        == b"v3 content"
    )


def test_version_records_uploader_and_comment(rest, storage):
    result = upload_document(
        rest,
        storage,
        CONFIG,
        "MSA",
        "Acme",
        b"v1",
        "pdf",
        uploaded_by="Priya",
        comment="Initial upload",
    )
    assert result.version_number == 1

    client = rest.select_one("clients", name="Acme")
    [version] = list_versions(rest, client["id"], "MSA")
    assert version.uploaded_by == "Priya"
    assert version.comment == "Initial upload"


def test_uploaded_by_and_comment_are_optional(rest, storage):
    result = upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v1", "pdf")
    assert result.version_number == 1

    client = rest.select_one("clients", name="Acme")
    [version] = list_versions(rest, client["id"], "MSA")
    assert version.uploaded_by is None
    assert version.comment is None


def test_client_documents_row_always_points_at_latest_version(rest, storage):
    # The "current" pointer used by gating/status checks must reflect the
    # newest upload, even though every version is separately preserved.
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v1", "pdf")
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v2 final", "pdf")

    client = rest.select_one("clients", name="Acme")
    current = rest.select_one(
        "client_documents", client_id=client["id"], doc_type="MSA"
    )
    assert storage.get(current["storage_path"]) == b"v2 final"


def test_list_document_versions_via_client_name(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v1", "pdf")
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v2", "pdf")

    versions = list_document_versions(rest, "Acme", "MSA")
    assert [v.version_number for v in versions] == [1, 2]


def test_list_document_versions_unknown_client_raises(rest, storage):
    with pytest.raises(ClientDocumentNotFound):
        list_document_versions(rest, "Ghost", "MSA")


def test_get_document_version_returns_specific_version_content(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v1 content", "pdf")
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v2 content", "pdf")

    result = get_document_version(rest, storage, "Acme", "MSA", 1)
    assert result.content == b"v1 content"


def test_get_document_version_missing_version_raises(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v1", "pdf")

    with pytest.raises(ClientDocumentNotFound):
        get_document_version(rest, storage, "Acme", "MSA", 99)


def test_restore_creates_new_version_and_keeps_all_prior_ones(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v1 content", "pdf")
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v2 content", "pdf")
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v3 content", "pdf")

    result = restore_document_version(
        rest, storage, "Acme", "MSA", 1, uploaded_by="Priya"
    )

    # Restoring creates a brand new version rather than deleting/rewriting history.
    assert result.version_number == 4

    client = rest.select_one("clients", name="Acme")
    versions = list_versions(rest, client["id"], "MSA")
    assert [v.version_number for v in versions] == [1, 2, 3, 4]
    assert (
        get_version_content(rest, storage, client["id"], "MSA", 1).content
        == b"v1 content"
    )
    assert (
        get_version_content(rest, storage, client["id"], "MSA", 4).content
        == b"v1 content"
    )

    # And the current pointer now reflects the restored content.
    current = rest.select_one(
        "client_documents", client_id=client["id"], doc_type="MSA"
    )
    assert storage.get(current["storage_path"]) == b"v1 content"


def test_restore_default_comment_notes_which_version(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v1", "pdf")
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v2", "pdf")

    restore_document_version(rest, storage, "Acme", "MSA", 1)

    client = rest.select_one("clients", name="Acme")
    versions = list_versions(rest, client["id"], "MSA")
    assert versions[-1].comment == "Restored from version 1"


def test_restore_unknown_client_raises(rest, storage):
    with pytest.raises(ClientDocumentNotFound):
        restore_document_version(rest, storage, "Ghost", "MSA", 1)


def test_restore_unknown_version_raises(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v1", "pdf")

    with pytest.raises(ClientDocumentNotFound):
        restore_document_version(rest, storage, "Acme", "MSA", 99)


def test_upload_document_retries_and_succeeds_after_a_version_number_conflict(
    rest, storage
):
    # Simulates the exact race two near-simultaneous uploads can hit: the
    # first attempt to record a reserved version number loses to a
    # concurrent upload that claimed it first. upload_document must retry
    # with a freshly reserved number rather than surfacing the raw conflict.
    real_record_version = version_service.record_version
    calls = {"count": 0}

    def flaky_record_version(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise VersionNumberConflict(
                "simulated race — another upload claimed this version first"
            )
        return real_record_version(*args, **kwargs)

    with patch(
        "app.services.document_service.version_service.record_version",
        side_effect=flaky_record_version,
    ):
        result = upload_document(
            rest, storage, CONFIG, "MSA", "Acme", b"content", "pdf"
        )

    assert calls["count"] == 2
    assert result.version_number == 1
    client = rest.select_one("clients", name="Acme")
    assert [v.version_number for v in list_versions(rest, client["id"], "MSA")] == [1]


def test_upload_document_gives_up_after_max_conflict_retries(rest, storage):
    with patch(
        "app.services.document_service.version_service.record_version",
        side_effect=VersionNumberConflict("simulated persistent race"),
    ):
        with pytest.raises(VersionNumberConflict):
            upload_document(rest, storage, CONFIG, "MSA", "Acme", b"content", "pdf")
