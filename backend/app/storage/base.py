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
    def make_dir(self, path: str) -> None:
        """Ensure a directory exists at `path` (and any parents)."""

    @abstractmethod
    def delete_dir(self, path: str) -> None:
        """Delete `path` and everything under it. No-op if it doesn't exist."""

    def web_url(self, path: str) -> str | None:
        """A real, clickable URL a person can open in a browser to view
        `path` directly (a SharePoint folder/file link, for example) — or
        None if this backend has no such concept (e.g. local disk) or the
        lookup fails for any reason. Deliberately non-abstract: this is a
        nice-to-have, never something a caller should treat as guaranteed,
        so a backend that can't provide one just returns None rather than
        every implementation having to stub it out."""
        return None
