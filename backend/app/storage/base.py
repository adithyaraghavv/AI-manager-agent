"""Storage backend interface.

The rest of the app (agent, API routes) talks only to this interface, never
to the filesystem or a specific cloud SDK directly. Swapping local storage
for SharePoint/Azure Blob later means writing one new implementation of this
class — no changes anywhere else.
"""
from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    def save(self, path: str, content: bytes) -> None:
        """Write `content` to `path`, creating any intermediate folders."""

    @abstractmethod
    def get(self, path: str) -> bytes:
        """Read and return the bytes at `path`. Raises FileNotFoundError if absent."""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Whether `path` exists."""

    @abstractmethod
    def list(self, prefix: str) -> list[str]:
        """List paths under `prefix` (non-recursive is fine for callers' needs today)."""

    @abstractmethod
    def delete(self, path: str) -> None:
        """Delete `path`. No-op if it doesn't exist."""

    @abstractmethod
    def make_dir(self, path: str) -> None:
        """Ensure a directory exists at `path` (and any parents)."""
