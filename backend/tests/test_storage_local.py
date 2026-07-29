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


def test_make_dir_and_list(storage):
    storage.make_dir("Client1/01_Pre-requisites")
    storage.make_dir("Client1/02_Requirement Analysis")
    entries = storage.list("Client1")
    assert len(entries) == 2


def test_path_escape_blocked(storage):
    with pytest.raises(ValueError):
        storage.save("../escape.txt", b"x")
