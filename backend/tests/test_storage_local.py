import pytest

from app.storage.local import LocalFilesystemStorage


@pytest.fixture
def storage(tmp_path):
    return LocalFilesystemStorage(tmp_path)


def test_save_and_get_roundtrip(storage):
    storage.save("Client1/01_Pre-requisites/file.txt", b"hello")
    assert storage.get("Client1/01_Pre-requisites/file.txt") == b"hello"


def test_exists(storage):
    assert not storage.exists("nope.txt")
    storage.save("nope.txt", b"x")
    assert storage.exists("nope.txt")


def test_get_missing_raises(storage):
    with pytest.raises(FileNotFoundError):
        storage.get("missing.txt")


def test_make_dir_creates_nested_dirs(storage):
    storage.make_dir("Client1/01_Pre-requisites")
    storage.make_dir("Client1/02_Requirement Analysis")
    assert storage.exists("Client1/01_Pre-requisites")
    assert storage.exists("Client1/02_Requirement Analysis")


def test_path_escape_blocked(storage):
    with pytest.raises(ValueError):
        storage.save("../escape.txt", b"x")


def test_delete_dir_removes_everything_under_it(storage):
    storage.save("Client1/01_Pre-requisites/file.txt", b"hello")
    storage.save("Client1/02_Requirement Analysis/other.txt", b"world")

    storage.delete_dir("Client1")

    assert not storage.exists("Client1")


def test_delete_dir_missing_is_a_noop(storage):
    storage.delete_dir("NeverExisted")  # should not raise


def test_delete_dir_refuses_to_wipe_storage_root(storage):
    storage.save("Client1/file.txt", b"x")
    with pytest.raises(ValueError):
        storage.delete_dir("")
    # Confirm nothing was actually touched
    assert storage.exists("Client1/file.txt")
