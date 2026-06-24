"""
File Storage Service
Manages template retrieval and document storage in structured folders.
"""

import os
import re
import shutil
import logging
from datetime import datetime
from typing import Optional, List
from models.schemas import DocumentType, DocumentInfo, TemplateInfo

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Base paths (relative to project root)
# ─────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR  = os.path.join(BASE_DIR, "..", "Templates")
CLIENTS_DIR    = os.path.join(BASE_DIR, "..", "Clients")


# ─────────────────────────────────────────────
# Template Helpers
# ─────────────────────────────────────────────

def get_template_path(document_type: DocumentType) -> Optional[str]:
    """
    Find a template file for the given document type.
    Looks for files like 'sow_template.docx', 'sow.docx', etc.
    """
    doc_lower = document_type.value.lower()
    if not os.path.exists(TEMPLATES_DIR):
        return None

    for fname in os.listdir(TEMPLATES_DIR):
        fname_lower = fname.lower()
        if doc_lower in fname_lower:
            return os.path.join(TEMPLATES_DIR, fname)
    return None


def list_templates() -> List[TemplateInfo]:
    """Return metadata for all available templates."""
    templates = []
    if not os.path.exists(TEMPLATES_DIR):
        return templates

    for fname in sorted(os.listdir(TEMPLATES_DIR)):
        fpath = os.path.join(TEMPLATES_DIR, fname)
        if not os.path.isfile(fpath):
            continue

        # Try to determine document type from filename
        doc_type = _detect_doc_type_from_filename(fname) or "UNKNOWN"
        size_kb = round(os.path.getsize(fpath) / 1024, 2)

        templates.append(TemplateInfo(
            name=fname.replace("_", " ").replace(".docx", "").title(),
            document_type=doc_type,
            filename=fname,
            download_url=f"/api/templates/download/{fname}",
            size_kb=size_kb,
        ))
    return templates


# ─────────────────────────────────────────────
# Document Storage
# ─────────────────────────────────────────────

def get_client_folder(client_name: str, document_type: DocumentType) -> str:
    """
    Construct the storage path for a client's document:
    Clients/{ClientName}/{DocumentType}/
    
    Sanitizes client name to be filesystem-safe.
    """
    safe_client = _sanitize_folder_name(client_name)
    folder = os.path.join(CLIENTS_DIR, safe_client, document_type.value)
    os.makedirs(folder, exist_ok=True)
    return folder


def store_document(
    source_path: str,
    client_name: str,
    document_type: DocumentType,
    original_filename: str,
) -> DocumentInfo:
    """
    Move an uploaded temp file into the correct client folder.
    Adds a timestamp suffix to prevent overwrites.
    """
    folder = get_client_folder(client_name, document_type)

    # Build timestamped filename: acme_sow_20240115_143022.docx
    base, ext = os.path.splitext(original_filename)
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_client = _sanitize_folder_name(client_name).lower()
    new_filename = f"{safe_client}_{document_type.value.lower()}_{timestamp}{ext}"

    dest_path = os.path.join(folder, new_filename)
    shutil.move(source_path, dest_path)

    size_kb = round(os.path.getsize(dest_path) / 1024, 2)
    return DocumentInfo(
        filename=new_filename,
        client_name=client_name,
        document_type=document_type.value,
        file_path=dest_path,
        uploaded_at=datetime.now().isoformat(),
        size_kb=size_kb,
    )


def list_client_documents(client_name: Optional[str] = None) -> List[DocumentInfo]:
    """
    List stored documents, optionally filtered by client.
    Returns newest-first.
    """
    results = []
    if not os.path.exists(CLIENTS_DIR):
        return results

    clients = [client_name] if client_name else os.listdir(CLIENTS_DIR)

    for client in clients:
        client_path = os.path.join(CLIENTS_DIR, client)
        if not os.path.isdir(client_path):
            continue

        for doc_type_folder in os.listdir(client_path):
            doc_folder = os.path.join(client_path, doc_type_folder)
            if not os.path.isdir(doc_folder):
                continue

            for fname in os.listdir(doc_folder):
                fpath = os.path.join(doc_folder, fname)
                if not os.path.isfile(fpath):
                    continue
                size_kb = round(os.path.getsize(fpath) / 1024, 2)
                mtime   = datetime.fromtimestamp(os.path.getmtime(fpath)).isoformat()
                results.append(DocumentInfo(
                    filename=fname,
                    client_name=client,
                    document_type=doc_type_folder,
                    file_path=fpath,
                    uploaded_at=mtime,
                    size_kb=size_kb,
                ))

    # Sort newest first
    results.sort(key=lambda x: x.uploaded_at or "", reverse=True)
    return results


def search_documents(query: str) -> List[DocumentInfo]:
    """Simple filename + client search."""
    q = query.lower()
    all_docs = list_client_documents()
    return [
        d for d in all_docs
        if q in d.filename.lower()
        or q in d.client_name.lower()
        or q in d.document_type.lower()
    ]


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _sanitize_folder_name(name: str) -> str:
    """Make a string safe to use as a folder name."""
    safe = re.sub(r'[<>:"/\\|?*]', "_", name)
    safe = safe.strip(". ")
    return safe or "Unknown"


def _detect_doc_type_from_filename(filename: str) -> Optional[str]:
    """Detect document type from filename string."""
    fname_upper = filename.upper()
    for doc_type in DocumentType:
        if doc_type.value in fname_upper:
            return doc_type.value
    return None


def detect_doc_type_from_content_or_filename(
    filename: str,
    content_text: str = ""
) -> Optional[DocumentType]:
    """
    Auto-detect document type from filename and optionally file content.
    Used during upload to pre-fill the document type field.
    """
    # Try filename first
    result = _detect_doc_type_from_filename(filename)
    if result:
        try:
            return DocumentType(result)
        except ValueError:
            pass

    # Try content keywords
    text_upper = content_text.upper()
    for doc_type, _keywords in {
        DocumentType.SOW: ["STATEMENT OF WORK", "SCOPE OF WORK"],
        DocumentType.FRD: ["FUNCTIONAL REQUIREMENT", "FUNCTIONAL SPECIFICATION"],
        DocumentType.HLD: ["HIGH LEVEL DESIGN", "HIGH-LEVEL DESIGN"],
        DocumentType.LLD: ["LOW LEVEL DESIGN", "LOW-LEVEL DESIGN"],
        DocumentType.BRD: ["BUSINESS REQUIREMENT", "BUSINESS ANALYSIS"],
        DocumentType.MSA: ["MASTER SERVICE AGREEMENT", "MSA"],
    }.items():
        if any(kw in text_upper for kw in _keywords):
            return doc_type

    return None
