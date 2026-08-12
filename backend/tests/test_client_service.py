from datetime import datetime, timedelta, timezone

import pytest

from app.core.phase_config import Phase, PhaseConfig
from app.services.client_service import (
    delete_client,
    existing_document_types,
    find_client,
    get_or_create_client,
    mark_document_not_applicable,
    not_applicable_document_types,
    purge_deleted_clients,
    satisfied_document_types,
    unmark_document_not_applicable,
)
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


def test_delete_client_hides_it_but_keeps_data_intact(rest, storage):
    # Soft-delete: invisible to normal lookups, but nothing is actually erased —
    # this is the recovery window added per team review feedback.
    client = get_or_create_client(rest, storage, CONFIG, "Acme")
    rest.insert("client_documents", {"client_id": client["id"], "doc_type": "MSA", "phase_name": "Pre-requisites"})
    assert storage.exists("Acme")

    delete_client(rest, storage, client)

    assert find_client(rest, "Acme") is None
    # ...but the underlying row, its documents, and its files are all still there.
    assert rest.select_one("clients", id=client["id"])["deleted_at"] is not None
    assert rest.select("client_documents", client_id=client["id"]) != []
    assert storage.exists("Acme")


def test_get_or_create_after_delete_creates_a_new_client_not_a_revival(rest, storage):
    original = get_or_create_client(rest, storage, CONFIG, "Acme")
    delete_client(rest, storage, original)

    revived = get_or_create_client(rest, storage, CONFIG, "Acme")

    assert revived["id"] != original["id"]
    # Both rows exist — the old (deleted) one and the new (active) one.
    assert len(rest.select("clients", name="Acme")) == 2


def test_purge_removes_clients_past_the_retention_window(rest, storage):
    client = get_or_create_client(rest, storage, CONFIG, "Acme")
    rest.insert("client_documents", {"client_id": client["id"], "doc_type": "MSA", "phase_name": "Pre-requisites"})
    old_deletion = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
    rest.update("clients", {"id": client["id"]}, {"deleted_at": old_deletion})

    purged = purge_deleted_clients(rest, storage, older_than_days=30)

    assert purged == ["Acme"]
    assert rest.select("clients", id=client["id"]) == []
    assert rest.select("client_documents", client_id=client["id"]) == []
    assert not storage.exists("Acme")


def test_purge_leaves_recently_deleted_clients_alone(rest, storage):
    client = get_or_create_client(rest, storage, CONFIG, "Acme")
    delete_client(rest, storage, client)  # deleted "now", well within the window

    purged = purge_deleted_clients(rest, storage, older_than_days=30)

    assert purged == []
    assert rest.select_one("clients", id=client["id"]) is not None
    assert storage.exists("Acme")


def test_purge_leaves_active_clients_alone(rest, storage):
    get_or_create_client(rest, storage, CONFIG, "Acme")

    purged = purge_deleted_clients(rest, storage, older_than_days=30)

    assert purged == []
    assert find_client(rest, "Acme") is not None


def test_delete_client_does_not_affect_other_clients(rest, storage):
    acme = get_or_create_client(rest, storage, CONFIG, "Acme")
    get_or_create_client(rest, storage, CONFIG, "Globex")

    delete_client(rest, storage, acme)

    assert find_client(rest, "Globex") is not None
    assert storage.exists("Globex")


def test_get_or_create_client_is_case_insensitive(rest, storage):
    # The exact bug this guards against: typing "hillenbrand" for an existing
    # "Hillenbrand" must resolve to the SAME client, not create a second one.
    created = get_or_create_client(rest, storage, CONFIG, "Hillenbrand")
    found_lowercase = get_or_create_client(rest, storage, CONFIG, "hillenbrand")

    assert found_lowercase["id"] == created["id"]
    assert len(rest.select("clients")) == 1


def test_get_or_create_client_uses_canonical_casing_for_storage_folder(rest, storage):
    # Even when looked up under different casing, the folder created/reused
    # must be the one matching the ORIGINAL stored name — otherwise a
    # case-sensitive filesystem (Linux) would end up with two folders for
    # what the database considers one client.
    get_or_create_client(rest, storage, CONFIG, "Hillenbrand")
    get_or_create_client(rest, storage, CONFIG, "HILLENBRAND")

    assert storage.exists("Hillenbrand")
    assert not storage.exists("HILLENBRAND")


def test_find_client_is_case_insensitive(rest, storage):
    get_or_create_client(rest, storage, CONFIG, "Hillenbrand")
    assert find_client(rest, "hillenbrand") is not None
    assert find_client(rest, "HILLENBRAND") is not None


def test_mark_document_not_applicable_adds_to_satisfied_but_not_existing(rest, storage):
    client = get_or_create_client(rest, storage, CONFIG, "Acme")

    mark_document_not_applicable(rest, client, "BRD", reason="Client provided finished requirements in the SOW")

    # Not actually filed — existing_document_types (real filings) is untouched.
    assert existing_document_types(rest, client) == set()
    # But it IS counted as not-applicable, and satisfied combines both.
    assert not_applicable_document_types(rest, client) == {"BRD"}
    assert satisfied_document_types(rest, client) == {"BRD"}


def test_mark_document_not_applicable_is_idempotent(rest, storage):
    client = get_or_create_client(rest, storage, CONFIG, "Acme")

    mark_document_not_applicable(rest, client, "BRD", reason="first reason")
    mark_document_not_applicable(rest, client, "BRD", reason="updated reason")

    # Still just one mark, not two — and the reason was updated, not duplicated.
    rows = rest.select("not_applicable_documents", client_id=client["id"], doc_type="BRD")
    assert len(rows) == 1
    assert rows[0]["reason"] == "updated reason"


def test_unmark_document_not_applicable_reverses_it(rest, storage):
    client = get_or_create_client(rest, storage, CONFIG, "Acme")
    mark_document_not_applicable(rest, client, "BRD")

    was_marked = unmark_document_not_applicable(rest, client, "BRD")

    assert was_marked is True
    assert not_applicable_document_types(rest, client) == set()
    assert satisfied_document_types(rest, client) == set()


def test_unmark_document_not_applicable_no_op_if_never_marked(rest, storage):
    client = get_or_create_client(rest, storage, CONFIG, "Acme")

    was_marked = unmark_document_not_applicable(rest, client, "BRD")

    assert was_marked is False
