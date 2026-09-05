import pytest

from app.db.purge_clients_except import purge_clients_except
from app.storage.local import LocalFilesystemStorage


@pytest.fixture
def storage(tmp_path):
    return LocalFilesystemStorage(tmp_path)


def _make_client(rest, storage, name):
    client = rest.insert("clients", {"name": name})
    storage.make_dir(name)
    rest.insert("client_documents", {"client_id": client["id"], "doc_type": "MSA"})
    rest.insert(
        "document_versions",
        {"client_id": client["id"], "doc_type": "MSA", "version_number": 1},
    )
    rest.insert("not_applicable_documents", {"client_id": client["id"], "doc_type": "SOW"})
    rest.insert("sow_metadata", {"client_id": client["id"], "contract_value": 1000})
    return client


def test_dry_run_reports_but_does_not_delete(rest, storage):
    keep = _make_client(rest, storage, "Lilly")
    drop = _make_client(rest, storage, "Ghost Client")

    purged = purge_clients_except(rest, storage, ["Lilly"], apply=False)

    assert purged == ["Ghost Client"]
    assert rest.select_one("clients", id=keep["id"]) is not None
    assert rest.select_one("clients", id=drop["id"]) is not None  # untouched


def test_apply_removes_client_and_every_related_row(rest, storage):
    keep = _make_client(rest, storage, "Lilly")
    drop = _make_client(rest, storage, "Ghost Client")

    purged = purge_clients_except(rest, storage, ["Lilly"], apply=True)

    assert purged == ["Ghost Client"]
    assert rest.select_one("clients", id=keep["id"]) is not None  # untouched
    assert rest.select_one("clients", id=drop["id"]) is None
    assert rest.select("client_documents", client_id=drop["id"]) == []
    assert rest.select("document_versions", client_id=drop["id"]) == []
    assert rest.select("not_applicable_documents", client_id=drop["id"]) == []
    assert rest.select("sow_metadata", client_id=drop["id"]) == []
    assert not storage.exists("Ghost Client")


def test_apply_leaves_kept_clients_data_fully_intact(rest, storage):
    keep = _make_client(rest, storage, "Lilly")
    _make_client(rest, storage, "Ghost Client")

    purge_clients_except(rest, storage, ["Lilly"], apply=True)

    assert rest.select("client_documents", client_id=keep["id"]) != []
    assert rest.select("document_versions", client_id=keep["id"]) != []
    assert rest.select("not_applicable_documents", client_id=keep["id"]) != []
    assert rest.select("sow_metadata", client_id=keep["id"]) != []
    assert storage.exists("Lilly")


def test_keep_name_matching_is_case_and_whitespace_insensitive(rest, storage):
    keep = _make_client(rest, storage, "Hillenbrand-AI")
    drop = _make_client(rest, storage, "Ghost Client")

    purged = purge_clients_except(rest, storage, [" hillenbrand-ai "], apply=True)

    assert purged == ["Ghost Client"]
    assert rest.select_one("clients", id=keep["id"]) is not None
    assert rest.select_one("clients", id=drop["id"]) is None


def test_nothing_to_purge_when_every_client_is_kept(rest, storage):
    _make_client(rest, storage, "Lilly")
    _make_client(rest, storage, "SiriusXM")

    purged = purge_clients_except(rest, storage, ["Lilly", "SiriusXM"], apply=True)

    assert purged == []
