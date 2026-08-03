import pytest

from app.core.phase_config import Phase, PhaseConfig
from app.services.document_service import (
    GatingBlocked,
    TemplateNotFound,
    request_template,
    upload_document,
)
from app.storage.local import LocalFilesystemStorage

CONFIG = PhaseConfig(
    [
        Phase(name="Pre-requisites", sequence=1, required_documents=("MSA", "SOW")),
        Phase(name="Requirement Analysis", sequence=2, required_documents=("BRD",)),
    ]
)


@pytest.fixture
def client_storage(tmp_path):
    return LocalFilesystemStorage(tmp_path / "clients")


@pytest.fixture
def template_storage(tmp_path):
    storage = LocalFilesystemStorage(tmp_path / "templates")
    storage.save("MSA.txt", b"mock MSA template")
    storage.save("BRD.txt", b"mock BRD template")
    return storage


def _seed_template_row(rest, doc_type: str, filename: str):
    rest.insert("templates", {"doc_type": doc_type, "storage_path": filename, "filename": filename})


def test_request_template_succeeds_for_phase_one_regardless_of_status(rest, client_storage, template_storage):
    _seed_template_row(rest, "MSA", "MSA.txt")
    result = request_template(rest, client_storage, template_storage, CONFIG, "MSA", "Acme")
    assert result.content == b"mock MSA template"


def test_request_template_blocked_for_phase_two_until_phase_one_filed(rest, client_storage, template_storage):
    _seed_template_row(rest, "BRD", "BRD.txt")
    with pytest.raises(GatingBlocked) as exc:
        request_template(rest, client_storage, template_storage, CONFIG, "BRD", "Acme")
    assert set(exc.value.decision.missing_documents) == {"MSA", "SOW"}


def test_request_template_missing_from_db_raises_not_found(rest, client_storage, template_storage):
    with pytest.raises(TemplateNotFound):
        request_template(rest, client_storage, template_storage, CONFIG, "MSA", "Acme")


def test_upload_then_request_unlocks_next_phase(rest, client_storage, template_storage):
    _seed_template_row(rest, "BRD", "BRD.txt")

    # Phase-2 template blocked before phase-1 docs are filed.
    with pytest.raises(GatingBlocked):
        request_template(rest, client_storage, template_storage, CONFIG, "BRD", "Acme")

    upload_document(rest, client_storage, CONFIG, "MSA", "Acme", b"filled msa", "pdf")
    upload_document(rest, client_storage, CONFIG, "SOW", "Acme", b"filled sow", "pdf")

    # Now unlocked.
    result = request_template(rest, client_storage, template_storage, CONFIG, "BRD", "Acme")
    assert result.content == b"mock BRD template"


def test_upload_blocked_for_phase_two_until_phase_one_complete(rest, client_storage, template_storage):
    with pytest.raises(GatingBlocked):
        upload_document(rest, client_storage, CONFIG, "BRD", "Acme", b"filled brd", "pdf")


def test_reupload_same_doc_type_updates_existing_record_not_duplicate(rest, client_storage, template_storage):
    upload_document(rest, client_storage, CONFIG, "MSA", "Acme", b"v1", "pdf")
    upload_document(rest, client_storage, CONFIG, "MSA", "Acme", b"v2", "pdf")

    client = rest.select_one("clients", name="Acme")
    records = rest.select("client_documents", client_id=client["id"], doc_type="MSA")
    assert len(records) == 1


def test_upload_with_different_casing_files_under_the_same_client_and_folder(rest, client_storage, template_storage):
    # The exact bug this guards against: uploading as "Acme" then "acme" must
    # be treated as the SAME client and land in the SAME storage folder — not
    # a second client record with a second, differently-cased folder.
    upload_document(rest, client_storage, CONFIG, "MSA", "Acme", b"v1", "pdf")
    result = upload_document(rest, client_storage, CONFIG, "SOW", "acme", b"v2", "pdf")

    assert len(rest.select("clients")) == 1
    assert result.stored_path.startswith("Acme/")  # canonical casing, not "acme/"
    assert client_storage.exists("Acme/01_Pre-requisites")
    assert not client_storage.exists("acme")
