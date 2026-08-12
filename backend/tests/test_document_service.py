import pytest

from app.core.phase_config import Phase, PhaseConfig
from app.core.upload_validation import InvalidUpload, MAX_UPLOAD_SIZE_BYTES
from app.services.document_service import (
    ClientDocumentNotFound,
    GatingBlocked,
    TemplateFileMissing,
    TemplateNotFound,
    get_document_location,
    get_stored_document,
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


def test_upload_rejects_disallowed_file_type(rest, client_storage, template_storage):
    with pytest.raises(InvalidUpload, match="not allowed"):
        upload_document(rest, client_storage, CONFIG, "MSA", "Acme", b"malicious", "exe")


def test_upload_rejects_empty_file(rest, client_storage, template_storage):
    with pytest.raises(InvalidUpload, match="empty"):
        upload_document(rest, client_storage, CONFIG, "MSA", "Acme", b"", "pdf")


def test_upload_rejects_oversized_file(rest, client_storage, template_storage):
    oversized = b"x" * (MAX_UPLOAD_SIZE_BYTES + 1)
    with pytest.raises(InvalidUpload, match="too large"):
        upload_document(rest, client_storage, CONFIG, "MSA", "Acme", oversized, "pdf")


def test_request_template_with_record_but_no_local_file_gives_actionable_error(rest, client_storage, template_storage):
    # The exact bug this guards against: a fresh clone/environment has the
    # database row (shared across every environment) but never ran the local
    # seed script, so the file itself doesn't exist there. Must fail with a
    # clear "run this command" message, not a raw FileNotFoundError/500.
    _seed_template_row(rest, "MSA", "does_not_exist_on_disk.txt")
    with pytest.raises(TemplateFileMissing, match="seed_templates"):
        request_template(rest, client_storage, template_storage, CONFIG, "MSA", "Acme")


def test_get_stored_document_with_record_but_no_local_file_gives_actionable_error(rest, client_storage, template_storage):
    upload_document(rest, client_storage, CONFIG, "MSA", "Acme", b"filled msa", "pdf")
    client_storage.delete_dir("Acme")  # simulate: DB row exists, local file doesn't

    with pytest.raises(ClientDocumentNotFound, match="local storage"):
        get_stored_document(rest, client_storage, "Acme", "MSA")


def test_get_document_location_returns_folder_not_filename(rest, client_storage, template_storage):
    result = upload_document(rest, client_storage, CONFIG, "MSA", "Acme", b"filled msa", "pdf")

    location = get_document_location(rest, "Acme", "MSA")

    assert location.client_name == "Acme"
    assert location.doc_type == "MSA"
    assert location.folder_path == "Acme/01_Pre-requisites"
    assert location.folder_path == result.stored_path.rsplit("/", 1)[0]
    assert location.filename == result.filename


def test_get_document_location_unknown_client_raises(rest, client_storage, template_storage):
    with pytest.raises(ClientDocumentNotFound):
        get_document_location(rest, "Ghost", "MSA")


def test_get_document_location_unfiled_doc_type_raises(rest, client_storage, template_storage):
    upload_document(rest, client_storage, CONFIG, "MSA", "Acme", b"filled msa", "pdf")

    with pytest.raises(ClientDocumentNotFound):
        get_document_location(rest, "Acme", "SOW")
