"""Validates a client name is safe to use as a storage folder segment.

Unlike document filenames (see file_naming.slugify, which strips unsafe
characters down to a clean slug), a client name is used as-is for both
display (DB record, chat replies) and as a literal folder name — so instead
of silently mangling what the PM typed, this rejects the handful of
characters that would either escape the storage root (".." path segments)
or produce a confusing/unintended folder structure (path separators), plus
anything SharePoint itself refuses in a file/folder name. The latter never
mattered on local disk, but a client name becomes a literal SharePoint
folder name when STORAGE_BACKEND=sharepoint, and Graph rejects these with
an opaque API error rather than a friendly one — see
https://support.microsoft.com/en-us/office/restrictions-and-limitations-in-onedrive-and-sharepoint-64883a5d-228e-48f5-b3d2-eb39e07630fa
"""

_DISALLOWED_SUBSTRINGS = ("..", "/", "\\")

# SharePoint/OneDrive's own forbidden characters in a file or folder name.
_SHAREPOINT_FORBIDDEN_CHARS = '"*:<>?|'

# Reserved Windows/NTFS device names — SharePoint inherits this restriction
# even though the client name is never a real Windows path.
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(10)),
    *(f"LPT{i}" for i in range(10)),
}


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
    for bad in _SHAREPOINT_FORBIDDEN_CHARS:
        if bad in name:
            raise InvalidClientName(
                f"Client name {client_name!r} contains {bad!r}, which isn't allowed "
                "in a SharePoint file or folder name."
            )
    
    if name.upper() in _RESERVED_NAMES:
        raise InvalidClientName(
            f"Client name {client_name!r} is a reserved name and can't be used "
            "as a SharePoint folder name."
        )