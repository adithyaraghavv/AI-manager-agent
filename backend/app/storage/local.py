"""Local filesystem implementation of StorageBackend. Used for the POC;
swapped for SharePoint/Blob storage once cloud access is available."""

import shutil
from pathlib import Path

from app.storage.base import StorageBackend


class LocalFilesystemStorage(StorageBackend):
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve(self, path: str) -> Path:
        full = (self.root / path).resolve()
        if self.root not in full.parents and full != self.root:
            raise ValueError(f"Path {path!r} escapes storage root")
        return full

    def save(self, path: str, content: bytes) -> None:
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def get(self, path: str) -> bytes:
        target = self._resolve(path)
        if not target.is_file():
            raise FileNotFoundError(path)
        return target.read_bytes()

    def exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    def make_dir(self, path: str) -> None:
        self._resolve(path).mkdir(parents=True, exist_ok=True)

    def delete_dir(self, path: str) -> None:
        target = self._resolve(path)
        # Refuse to wipe the storage root itself — a blank/"." path would
        # otherwise resolve to `root` and delete every client's data at once.
        if target == self.root:
            raise ValueError("Refusing to delete the storage root itself")
        if target.is_dir():
            shutil.rmtree(target)

    def list(self, prefix: str) -> list[str]:
        target = self._resolve(prefix)
        if not target.is_dir():
            return []
        rel_prefix = target.relative_to(self.root)
        return sorted(
            str((rel_prefix / entry.name)).replace("\\", "/")
            for entry in target.iterdir()
        )
