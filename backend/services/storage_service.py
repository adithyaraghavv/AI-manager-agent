"""
File Storage Service
Manages dynamic template discovery and client document storage/retrieval.
"""

import os
import re
import shutil
import logging
from datetime import datetime
from typing import Optional, List, Tuple
from urllib.parse import quote

from models.schemas import TemplateInfo, DocumentInfo, ClientInfo

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".docx", ".doc", ".pdf", ".xlsx", ".pptx", ".txt"}
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

_this_file = os.path.abspath(__file__)
_services_dir = os.path.dirname(_this_file)
_backend_dir = os.path.dirname(_services_dir)
PROJECT_ROOT = os.path.abspath(os.path.join(_backend_dir, ".."))

TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "Templates")
CLIENTS_DIR = os.path.join(PROJECT_ROOT, "Clients")

# ─── Phase Subfolder Structure ─────────────────────────────────────────────────

CLIENT_SUBFOLDERS = [
    "1. Pre-requisites",
    "2. Requirement Analysis",
    "3. System Design",
    "4. Implementation (Coding)",
    "5. Testing (STLC integrated)",
    "6. Deployment",
    "7. Maintenance",
]

# Keyword lists → subfolder. Checked top-to-bottom; first match wins.
# More specific phrases must come before generic ones (e.g. "test summary" before "test").
_TYPE_TO_SUBFOLDER: List[Tuple[List[str], str]] = [
    (["kickoff", "kick off", "kick-off", "pre-req", "prerequisite", "pre requisite"],
     "1. Pre-requisites"),
    (["frd", "functional req", "brd", "business req"],
     "2. Requirement Analysis"),
    (["srs", "software req", "software requirement"],
     "3. System Design"),
    (["hld", "high level design", "high level", "lld", "low level design", "low level"],
     "4. Implementation (Coding)"),
    (["test summary", "test summary report"],
     "6. Deployment"),
    (["release note", "deployment", "go live", "go-live"],
     "6. Deployment"),
    (["test case", "test plan", "stlc", "defect log", "bug report", "qa plan", "uat"],
     "5. Testing (STLC integrated)"),
    (["data management", "dmp", "maintenance"],
     "7. Maintenance"),
]


# ─── Phase Routing Helpers ────────────────────────────────────────────────────

def _create_client_subfolders(client_folder: str) -> None:
    """Create all 7 standard phase subfolders inside a client folder."""
    for name in CLIENT_SUBFOLDERS:
        os.makedirs(os.path.join(client_folder, name), exist_ok=True)


def _detect_phase_folder(document_type: str, filename: str = "") -> str:
    """
    Determine which phase subfolder a document belongs to based on its
    document_type field and/or filename. Returns the subfolder name string.
    Falls back to "1. Pre-requisites" for unrecognised types.
    """
    combined = re.sub(r"[_\-]+", " ", (document_type + " " + filename).lower())
    for keywords, subfolder in _TYPE_TO_SUBFOLDER:
        for kw in keywords:
            if kw in combined:
                return subfolder
    return "1. Pre-requisites"


# ─── Utilities ────────────────────────────────────────────────────────────────

def _is_valid_document(filename: str) -> bool:
    _, ext = os.path.splitext(filename)
    return ext.lower() in ALLOWED_EXTENSIONS


def _sanitize_folder_name(name: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*]', "_", name)
    safe = safe.strip(". ")
    return safe or "Unknown"


def _display_name_from_filename(filename: str) -> str:
    """Convert filename to a readable display name."""
    name_no_ext = os.path.splitext(filename)[0]
    name_no_ext = re.sub(r"\(.*?\)", "", name_no_ext)  # remove (QMS-126) etc.
    name_no_ext = re.sub(r"[_\-]+", " ", name_no_ext)
    name_no_ext = re.sub(r"\s+", " ", name_no_ext)
    return name_no_ext.strip()


# ─── Templates ────────────────────────────────────────────────────────────────

def list_templates() -> List[TemplateInfo]:
    """Dynamically discover all valid template files from the Templates directory."""
    if not os.path.exists(TEMPLATES_DIR):
        logger.warning("Templates directory not found: %s", TEMPLATES_DIR)
        return []

    templates: List[TemplateInfo] = []
    for fname in sorted(os.listdir(TEMPLATES_DIR)):
        fpath = os.path.join(TEMPLATES_DIR, fname)
        if not os.path.isfile(fpath):
            continue
        if not _is_valid_document(fname):
            continue
        _, ext = os.path.splitext(fname)
        size_kb = round(os.path.getsize(fpath) / 1024, 2)
        display_name = _display_name_from_filename(fname)
        templates.append(TemplateInfo(
            name=display_name,
            document_type=display_name,
            filename=fname,
            extension=ext.lower(),
            download_url=f"/api/templates/download/{quote(fname)}",
            size_kb=size_kb,
        ))
    return templates


def get_template_path(filename: str) -> Optional[str]:
    """Validate and return the absolute path of a template by filename."""
    safe = os.path.basename(filename)
    path = os.path.join(TEMPLATES_DIR, safe)
    if os.path.isfile(path) and _is_valid_document(safe):
        return path
    return None


# Phrases in template names → their common abbreviations (appended to searchable text)
_PHRASE_TO_ABBREV: dict[str, str] = {
    "high level design":                  "hld",
    "low level design":                   "lld",
    "software requirements specification": "srs",
    "data management plan":               "dmp",
    "functional requirement":             "frd",
}

# Phrases in user QUERIES → abbreviations to add to q_tokens for better matching
_QUERY_PHRASE_TO_ABBREV: dict[str, str] = {
    "functional requirement": "frd",
    "high level design":      "hld",
    "low level design":       "lld",
    "software requirements":  "srs",
    "data management plan":   "dmp",
}


def _enrich_searchable(text: str) -> str:
    """Append abbreviations for any spelled-out phrases found in template text."""
    extras: list[str] = []
    for phrase, abbrev in _PHRASE_TO_ABBREV.items():
        if phrase in text:
            extras.append(abbrev)
    return (text + " " + " ".join(extras)) if extras else text


def _enrich_query_tokens(q_norm: str, tokens: set) -> set:
    """If query contains a spelled-out phrase, add its abbreviation to token set."""
    extra: set = set()
    for phrase, abbrev in _QUERY_PHRASE_TO_ABBREV.items():
        if phrase in q_norm:
            extra.add(abbrev)
    return tokens | extra


def find_best_template(
    query: str,
    document_type: Optional[str] = None,
    minimum_score: float = 0.3,
) -> Optional[TemplateInfo]:
    """Find the best matching template using fuzzy + token-overlap scoring."""
    import difflib
    templates = list_templates()
    if not templates:
        return None

    q_norm = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
    q_tokens = _enrich_query_tokens(
        q_norm, {t for t in q_norm.split() if len(t) > 1}
    )
    best: Optional[TemplateInfo] = None
    best_score = 0.0

    for t in templates:
        searchable_raw = f"{t.name} {t.filename} {t.document_type or ''}".lower()
        searchable = _enrich_searchable(re.sub(r"[^a-z0-9]+", " ", searchable_raw).strip())
        s_tokens = {tok for tok in searchable.split() if len(tok) > 1}

        score = difflib.SequenceMatcher(None, q_norm, searchable).ratio()

        # Token overlap bonus (critical for abbreviation queries)
        if q_tokens:
            overlap = len(q_tokens & s_tokens) / len(q_tokens)
            score += overlap * 1.2

        # Exact substring bonus
        if q_norm and q_norm in searchable:
            score += 0.7

        # Explicit document_type hint bonus
        if document_type:
            dt_norm = re.sub(r"[^a-z0-9]+", " ", document_type.lower()).strip()
            if dt_norm and dt_norm in searchable:
                score += 1.2

        if score > best_score:
            best_score = score
            best = t

    return best if (best and best_score >= minimum_score) else None


# ─── Client Discovery ─────────────────────────────────────────────────────────

def _extract_client_name_from_folder(folder_name: str) -> str:
    """Extract readable client name from folder like Clients_XYZ_FRD → XYZ."""
    remainder = re.sub(r"^[Cc]lients?_?", "", folder_name)
    parts = remainder.rsplit("_", 1)
    if (len(parts) == 2
            and parts[1].isupper()
            and len(parts[1]) <= 12
            and not any(c.isdigit() for c in parts[1])):
        return parts[0]
    return remainder or folder_name


def _discover_client_locations() -> List[Tuple[str, str, str]]:
    """
    Find all client document storage locations.
    Returns list of (client_name, folder_display_name, absolute_path).
    """
    seen: set = set()
    locations: List[Tuple[str, str, str]] = []

    # Standard structure: CLIENTS_DIR/client_name/
    if os.path.isdir(CLIENTS_DIR):
        for entry in sorted(os.listdir(CLIENTS_DIR)):
            fpath = os.path.join(CLIENTS_DIR, entry)
            real_path = os.path.realpath(fpath)
            if os.path.isdir(fpath) and real_path not in seen:
                seen.add(real_path)
                locations.append((entry, entry, fpath))

    # Legacy / flat structure: PROJECT_ROOT/Clients_*/
    if os.path.isdir(PROJECT_ROOT):
        for entry in sorted(os.listdir(PROJECT_ROOT)):
            if not re.match(r"^[Cc]lients?_", entry):
                continue
            fpath = os.path.join(PROJECT_ROOT, entry)
            real_path = os.path.realpath(fpath)
            if os.path.isdir(fpath) and real_path not in seen:
                seen.add(real_path)
                client_name = _extract_client_name_from_folder(entry)
                locations.append((client_name, entry, fpath))

    return locations


def _collect_documents_in_folder(
    client_name: str, folder_path: str
) -> List[DocumentInfo]:
    """Collect all valid documents in a client folder (recursive, 2 levels)."""
    docs: List[DocumentInfo] = []

    def _scan(dir_path: str, depth: int = 0):
        if not os.path.isdir(dir_path) or depth > 2:
            return
        try:
            entries = sorted(os.listdir(dir_path))
        except PermissionError:
            return
        for fname in entries:
            fpath = os.path.join(dir_path, fname)
            if os.path.isfile(fpath) and _is_valid_document(fname):
                _, ext = os.path.splitext(fname)
                try:
                    size_kb = round(os.path.getsize(fpath) / 1024, 2)
                    mtime = datetime.fromtimestamp(
                        os.path.getmtime(fpath)
                    ).isoformat()
                except OSError:
                    size_kb = 0.0
                    mtime = None
                rel = os.path.relpath(fpath, PROJECT_ROOT).replace("\\", "/")
                docs.append(DocumentInfo(
                    filename=fname,
                    display_name=_display_name_from_filename(fname),
                    client_name=client_name,
                    extension=ext.lower(),
                    file_path=fpath,
                    uploaded_at=mtime,
                    size_kb=size_kb,
                    download_url=f"/api/documents/client-file?path={quote(rel)}",
                ))
            elif os.path.isdir(fpath):
                _scan(fpath, depth + 1)

    _scan(folder_path)
    return sorted(docs, key=lambda d: d.uploaded_at or "", reverse=True)


def list_all_clients() -> List[ClientInfo]:
    """List all clients with their stored documents."""
    clients: List[ClientInfo] = []
    for client_name, folder_name, folder_path in _discover_client_locations():
        docs = _collect_documents_in_folder(client_name, folder_path)
        clients.append(ClientInfo(
            client_name=client_name,
            folder_name=folder_name,
            document_count=len(docs),
            documents=docs,
        ))
    return sorted(clients, key=lambda c: c.client_name.lower())


def find_client_documents(query_client: str) -> Optional[ClientInfo]:
    """Find a client by name (exact then partial match)."""
    q = query_client.strip().lower()
    locations = _discover_client_locations()
    if not locations:
        return None

    for client_name, folder_name, folder_path in locations:
        if client_name.lower() == q or folder_name.lower() == q:
            docs = _collect_documents_in_folder(client_name, folder_path)
            return ClientInfo(
                client_name=client_name,
                folder_name=folder_name,
                document_count=len(docs),
                documents=docs,
            )

    for client_name, folder_name, folder_path in locations:
        if q in client_name.lower() or q in folder_name.lower():
            docs = _collect_documents_in_folder(client_name, folder_path)
            return ClientInfo(
                client_name=client_name,
                folder_name=folder_name,
                document_count=len(docs),
                documents=docs,
            )

    return None


# Keywords for scoring a stored document against a requested type
_DOC_TYPE_KEYWORDS: dict[str, list[str]] = {
    "frd": ["frd", "functional requirement", "functional req"],
    "brd": ["brd", "business requirement"],
    "srs": ["srs", "software requirement", "software req"],
    "hld": ["hld", "high level design", "high level"],
    "lld": ["lld", "low level design", "low level"],
    "dmp": ["dmp", "data management"],
    "kickoff": ["kickoff", "kick off", "kick-off", "project kick"],
    "test": ["test case", "test plan", "uat", "stlc", "defect"],
    "test summary": ["test summary"],
    "release": ["release note", "deployment", "go live", "go-live"],
}


def _canonical_doc_type(doc_type: str) -> str:
    """Map a free-text document type to a canonical bucket key."""
    n = re.sub(r"[^a-z0-9]+", " ", (doc_type or "").lower()).strip()
    if not n:
        return ""
    # Direct abbreviation
    for key in ("frd", "brd", "srs", "hld", "lld", "dmp"):
        if key in n.split():
            return key
    # Phrase match
    for key, kws in _DOC_TYPE_KEYWORDS.items():
        for kw in kws:
            if kw in n:
                return key
    return n  # fall back to raw normalised text


def find_client_document_by_type(
    client_name: str, document_type: str
) -> Optional[DocumentInfo]:
    """
    Find the best matching stored document for a given client + doc type.
    e.g. client='Hillenbrand', document_type='LLD' → returns that client's LLD file.
    Returns None if the client is unknown or nothing matches.
    """
    client = find_client_documents(client_name)
    if not client or not client.documents:
        return None

    canon = _canonical_doc_type(document_type)
    keywords = _DOC_TYPE_KEYWORDS.get(canon, [canon]) if canon else []
    if not keywords:
        return None

    best: Optional[DocumentInfo] = None
    best_score = 0
    for doc in client.documents:
        haystack = re.sub(
            r"[_\-]+", " ",
            f"{doc.filename} {doc.display_name} {doc.document_type or ''}".lower(),
        )
        score = 0
        for kw in keywords:
            if kw in haystack:
                # Longer, more specific keywords score higher
                score += 2 if " " in kw else 1
        # Exact abbreviation as a whole token wins
        if canon and re.search(rf"\b{re.escape(canon)}\b", haystack):
            score += 3
        if score > best_score:
            best_score = score
            best = doc

    return best if best_score > 0 else None


def get_client_file_path(rel_path: str) -> Optional[str]:
    """
    Resolve a relative path and validate it is within an allowed client directory.
    Returns absolute path or None if invalid/unsafe.
    """
    normalized = rel_path.replace("/", os.sep).replace("\\", os.sep)
    abs_path = os.path.normpath(os.path.join(PROJECT_ROOT, normalized))
    project_root_abs = os.path.abspath(PROJECT_ROOT)

    if not abs_path.startswith(project_root_abs + os.sep):
        logger.warning("Path traversal attempt blocked: %s", rel_path)
        return None

    abs_clients = os.path.abspath(CLIENTS_DIR)
    within_clients = abs_path.startswith(abs_clients + os.sep)

    within_legacy = False
    if not within_clients and os.path.isdir(PROJECT_ROOT):
        for entry in os.listdir(PROJECT_ROOT):
            if re.match(r"^[Cc]lients?_", entry):
                legacy = os.path.abspath(os.path.join(PROJECT_ROOT, entry))
                if abs_path.startswith(legacy + os.sep):
                    within_legacy = True
                    break

    if not (within_clients or within_legacy):
        return None

    if not os.path.isfile(abs_path):
        return None

    if not _is_valid_document(os.path.basename(abs_path)):
        return None

    return abs_path


# ─── Upload / Store ───────────────────────────────────────────────────────────

def get_client_folder(client_name: str) -> str:
    """
    Get (or create) the top-level folder for a client under CLIENTS_DIR.
    Always ensures all 7 phase subfolders exist — safe to call on existing clients.
    """
    safe_client = _sanitize_folder_name(client_name)
    folder = os.path.join(CLIENTS_DIR, safe_client)
    os.makedirs(folder, exist_ok=True)
    _create_client_subfolders(folder)
    return folder


def store_document(
    source_path: str,
    client_name: str,
    document_type: str,
    original_filename: str,
) -> DocumentInfo:
    """
    Store an uploaded document in the correct phase subfolder.

    Routing:
      FRD / BRD          → 2. Requirement Analysis
      SRS                → 3. System Design
      HLD / LLD          → 4. Implementation (Coding)
      Test cases / plans → 5. Testing (STLC integrated)
      Test Summary       → 6. Deployment
      Data Mgmt / DMP    → 7. Maintenance
      Everything else    → 1. Pre-requisites  (default)
    """
    client_folder = get_client_folder(client_name)
    phase_subfolder = _detect_phase_folder(document_type, original_filename)
    target_dir = os.path.join(client_folder, phase_subfolder)
    os.makedirs(target_dir, exist_ok=True)  # safety net for legacy/external folders

    _, ext = os.path.splitext(original_filename)
    ext = ext.lower()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_client = _sanitize_folder_name(client_name).lower()
    safe_type = re.sub(r"[^a-z0-9]+", "_", document_type.lower()).strip("_")
    new_filename = f"{safe_client}_{safe_type}_{timestamp}{ext}"
    dest_path = os.path.join(target_dir, new_filename)
    shutil.move(source_path, dest_path)

    size_kb = round(os.path.getsize(dest_path) / 1024, 2)
    rel = os.path.relpath(dest_path, PROJECT_ROOT).replace("\\", "/")
    return DocumentInfo(
        filename=new_filename,
        display_name=_display_name_from_filename(new_filename),
        client_name=client_name,
        document_type=document_type,
        extension=ext,
        file_path=dest_path,
        uploaded_at=datetime.now().isoformat(),
        size_kb=size_kb,
        download_url=f"/api/documents/client-file?path={quote(rel)}",
    )


# ─── Search ───────────────────────────────────────────────────────────────────

def search_documents(query: str) -> List[DocumentInfo]:
    """Search all client documents by filename or client name."""
    q = query.lower().strip()
    results: List[DocumentInfo] = []
    for client in list_all_clients():
        for doc in client.documents:
            if (q in doc.filename.lower()
                    or q in doc.client_name.lower()
                    or q in (doc.document_type or "").lower()):
                results.append(doc)
    return results


def list_client_documents(client_name: Optional[str] = None) -> List[DocumentInfo]:
    """Legacy helper: list documents optionally filtered by client."""
    all_clients = list_all_clients()
    docs: List[DocumentInfo] = []
    for c in all_clients:
        if client_name and c.client_name.lower() != client_name.lower():
            continue
        docs.extend(c.documents)
    return docs


def detect_doc_type_from_content_or_filename(
    filename: str, content_text: str = ""
) -> str:
    """
    Return a canonical document type name detected from filename (and optional
    extracted text). Used by the /upload/detect-type endpoint to pre-fill the
    document type field in the UI.
    """
    combined = re.sub(r"[_\-]+", " ", (filename + " " + content_text).lower())
    if any(kw in combined for kw in ["kickoff", "kick off", "kick-off"]):
        return "Kickoff Template"
    if any(kw in combined for kw in ["frd", "functional req"]):
        return "FRD"
    if any(kw in combined for kw in ["brd", "business req"]):
        return "BRD"
    if any(kw in combined for kw in ["srs", "software req"]):
        return "SRS"
    if any(kw in combined for kw in ["hld", "high level design", "high level"]):
        return "HLD"
    if any(kw in combined for kw in ["lld", "low level design", "low level"]):
        return "LLD"
    if any(kw in combined for kw in ["data management", "dmp"]):
        return "Data Management Plan"
    if any(kw in combined for kw in ["test summary"]):
        return "Test Summary Report"
    if any(kw in combined for kw in ["test case", "test plan", "uat", "defect"]):
        return "Test Document"
    return _display_name_from_filename(filename) or "Document"
