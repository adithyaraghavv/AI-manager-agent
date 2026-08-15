"""Validates a client name is safe to use as a storage folder segment.

Unlike document filenames (see file_naming.slugify, which strips unsafe
characters down to a clean slug), a client name is used as-is for both
display (DB record, chat replies) and as a literal folder name — so instead
of silently mangling what the PM typed, this rejects the handful of
characters that would either escape the storage root (".." path segments)
or produce a confusing/unintended folder structure (path separators).
"""
_DISALLOWED_SUBSTRINGS = ("..", "/", "\\")


class InvalidClientName(ValueError):
    """A ValueError subclass so every existing `except ValueError` handler
    (routes_documents.py, dispatch_tool's various tool branches) already
    catches this without needing a new except clause added everywhere."""


def validate_client_name(client_name: str) -> None:
    name = client_name.strip()
    if not name:
        raise InvalidClientName("Client name can't be empty.")
    for bad in _DISALLOWED_SUBSTRINGS:
        if bad in name:
            raise InvalidClientName(
                f"Client name {client_name!r} contains {bad!r}, which isn't allowed "
                "(it would break how the client's files are stored)."
            )
