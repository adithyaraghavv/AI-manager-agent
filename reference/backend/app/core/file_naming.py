"""Fixed file naming convention: Marlabs_<DocType>_<ClientName>_<Timestamp>."""
import re
from datetime import datetime, timezone

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9]+")


def slugify(value: str) -> str:
    slug = _UNSAFE_CHARS.sub("_", value).strip("_")
    if not slug:
        raise ValueError(f"Value {value!r} has no usable characters after sanitization")
    return slug


def build_filename(doc_type: str, client_name: str, extension: str, timestamp: datetime | None = None) -> str:
    """Build a filename following the Marlabs_<DocType>_<ClientName>_<Timestamp> convention.

    `extension` should not include the leading dot (e.g. "pdf", "docx").
    """
    ts = timestamp or datetime.now(timezone.utc)
    stamp = ts.strftime("%Y%m%dT%H%M%SZ")
    ext = extension.lstrip(".")
    return f"Marlabs_{slugify(doc_type)}_{slugify(client_name)}_{stamp}.{ext}"
