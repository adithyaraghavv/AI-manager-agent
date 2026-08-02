import pytest

from app.core.phase_config import Phase, PhaseConfig
from app.services.client_service import delete_client, find_client, get_or_create_client
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


def test_find_client_returns_none_without_creating_one(rest, storage):
    assert find_client(rest, "Ghost") is None
    # Confirm the lookup had no side effect — nothing got created
    assert rest.select("clients") == []
    assert not storage.exists("Ghost")


def test_find_client_returns_existing_client(rest, storage):
    created = get_or_create_client(rest, storage, CONFIG, "Acme")
    found = find_client(rest, "Acme")
    assert found == created


def test_delete_client_removes_db_rows_and_storage_folder(rest, storage):
    client = get_or_create_client(rest, storage, CONFIG, "Acme")
    rest.insert("client_documents", {"client_id": client["id"], "doc_type": "MSA", "phase_name": "Pre-requisites"})
    assert storage.exists("Acme")

    delete_client(rest, storage, client)

    assert find_client(rest, "Acme") is None
    assert rest.select("client_documents", client_id=client["id"]) == []
    assert not storage.exists("Acme")


def test_delete_client_does_not_affect_other_clients(rest, storage):
    acme = get_or_create_client(rest, storage, CONFIG, "Acme")
    get_or_create_client(rest, storage, CONFIG, "Globex")

    delete_client(rest, storage, acme)

    assert find_client(rest, "Globex") is not None
    assert storage.exists("Globex")
