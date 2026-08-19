from unittest.mock import MagicMock, patch

import pytest

from app.core.phase_config import Phase, PhaseConfig
from app.db.backfill_embeddings import backfill
from app.services.client_service import delete_client
from app.services.document_service import upload_document
from app.storage.local import LocalFilesystemStorage

CONFIG = PhaseConfig(
    [
        Phase(name="Pre-requisites", sequence=1, required_documents=("MSA", "SOW")),
        Phase(name="Requirement Analysis", sequence=2, required_documents=("BRD",)),
    ]
)


@pytest.fixture
def storage(tmp_path):
    return LocalFilesystemStorage(tmp_path)


def _mock_embeddings_response(count: int) -> MagicMock:
    response = MagicMock()
    response.data = [MagicMock(embedding=[1.0, 0.0]) for _ in range(count)]
    return response


def test_backfill_embeds_every_active_clients_documents(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"acme msa text", "txt")
    upload_document(rest, storage, CONFIG, "SOW", "Acme", b"acme sow text", "txt")
    upload_document(rest, storage, CONFIG, "BRD", "Acme", b"acme brd text", "txt")
    upload_document(rest, storage, CONFIG, "MSA", "Globex", b"globex msa text", "txt")

    with patch("app.services.embedding_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.embeddings.create.return_value = _mock_embeddings_response(1)
        stats = backfill(rest, storage)

    assert stats["documents_seen"] == 4
    assert stats["documents_embedded"] == 4
    assert stats["chunks_stored"] == 4
    assert len(rest.select("document_chunks")) == 4


def test_backfill_skips_soft_deleted_clients(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"acme text", "txt")
    client = rest.select_one("clients", name="Acme")
    delete_client(rest, storage, client)

    with patch("app.services.embedding_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.embeddings.create.return_value = _mock_embeddings_response(1)
        stats = backfill(rest, storage)

    assert stats["documents_seen"] == 0
    assert rest.select("document_chunks") == []


def test_backfill_uses_the_current_version_number(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v1", "txt")
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"v2 current", "txt")

    with patch("app.services.embedding_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.embeddings.create.return_value = _mock_embeddings_response(1)
        backfill(rest, storage)

    [row] = rest.select("document_chunks")
    assert row["version_number"] == 2
    assert row["content"] == "v2 current"


def test_backfill_is_safe_to_rerun(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"acme text", "txt")

    with patch("app.services.embedding_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.embeddings.create.return_value = _mock_embeddings_response(1)
        backfill(rest, storage)
        stats = backfill(rest, storage)

    assert stats["documents_embedded"] == 1
    # Replaced, not duplicated — still exactly one chunk row.
    assert len(rest.select("document_chunks")) == 1


def test_backfill_skips_missing_local_files_without_crashing(rest, storage):
    upload_document(rest, storage, CONFIG, "MSA", "Acme", b"acme text", "txt")
    client = rest.select_one("clients", name="Acme")
    document = rest.select_one("client_documents", client_id=client["id"], doc_type="MSA")
    # Simulate a file that vanished from disk (e.g. a botched migration) without
    # its DB row being cleaned up — backfill should notice and skip, not crash.
    (storage.root / document["storage_path"]).unlink()

    stats = backfill(rest, storage)

    assert stats["documents_seen"] == 1
    assert stats["documents_embedded"] == 0
