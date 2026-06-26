"""
File Storage Service
Manages template retrieval and management plan",Manages template retrieval and document storage in structured folders.
"""

import difflib
import os
import re
import shutil
import logging
from datetime import datetime
from typing import Optional, List
from urllib.parse import quote

from models.schemas import (
    DocumentType,
    DocumentInfo,
    TemplateInfo,
    document_type_to_display,
)

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "Templates")
CLIENTS_DIR = os.path.join(PROJECT_ROOT, "Clients")


SUPPORTED_TEMPLATE_ALIASES: dict[DocumentType, list[str]] = {
    DocumentType.FRD: [
        "frd",
        "functional requirement",
        "functional requirements",
        "functional requirements document",
        "functional specification",
        "functional spec",
    ],
    DocumentType.DATA_MANAGEMENT_PLAN: [

        "data management",
        "dmp",
        "data plan",
    ],
    DocumentType.HLD: [
        "hld",
        "high level design",
        "high-level design",
        "high level design document",
        "architecture document",
        "architecture doc",
        "solution design",
    ],
    DocumentType.LLD: [
        "lld",
        "low level design",
        "low-level design",
        "low level design document",
        "detailed design",
        "technical design",
    ],
    DocumentType.SOFTWARE_REQUIREMENTS: [
        "software requirements",
        "software requirement",
        "software requirements template",
        "software requirements specification",
        "srs",
        "requirements template",
        "requirements document",
        "requirements doc",
        "specification document",
    ],
}


def _normalize_text(value: str) -> str:
    value = os.path.splitext(value)[0]
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _tokenize(value: str) -> set[str]:
    normalized = _normalize_text(value)
    return {token for token in normalized.split() if len(token) > 1}


def _detect_supported_template_type(filename: str) -> Optional[DocumentType]:
    normalized = _normalize_text(filename)
    tokens = set(normalized.split())

    for template_type, aliases in SUPPORTED_TEMPLATE_ALIASES.items():
        for alias in aliases:
            alias_normalized = _normalize_text(alias)
            alias_tokens = set(alias_normalized.split())

            if alias_normalized in normalized or alias_tokens.issubset(tokens):
                return template_type

    return None


def list_templates() -> List[TemplateInfo]:
    templates: List[TemplateInfo] = []

    if not os.path.exists(TEMPLATES_DIR):
        return templates

    for fname in sorted(os.listdir(TEMPLATES_DIR)):
        fpath = os.path.join(TEMPLATES_DIR, fname)

        if not os.path.isfile(fpath):
            continue

        detected_template_type = _detect_supported_template_type(fname)

        if not detected_template_type:
            continue

        size_kb = round(os.path.getsize(fpath) / 1024, 2)

        templates.append(
            TemplateInfo(
                name=os.path.splitext(fname)[0].replace("_", " ").strip(),
                document_type=document_type_to_display(detected_template_type)
                or detected_template_type.value,
                filename=fname,
                download_url=f"/api/templates/download/{quote(fname)}",
                size_kb=size_kb,
            )
        )

    return templates


def get_template_path(document_type: DocumentType) -> Optional[str]:
    if not os.path.exists(TEMPLATES_DIR):
        return None

    for fname in os.listdir(TEMPLATES_DIR):
        detected_template_type = _detect_supported_template_type(fname)

        if detected_template_type == document_type:
            return os.path.join(TEMPLATES_DIR, fname)

    return None


def find_best_template(
    query: str,
    document_type: Optional[DocumentType] = None,
    minimum_score: float = 0.35,
) -> Optional[TemplateInfo]:
    templates = list_templates()

    if not templates:
        return None

    query_normalized = _normalize_text(query)
    query_tokens = _tokenize(query)

    if not query_normalized and not document_type:
        return None

    best_template = None
    best_score = 0.0

    for template in templates:
        template_detected_type = _detect_supported_template_type(template.filename)

        searchable_text = f"{template.name} {template.filename} {template.document_type or ''}"
        searchable_normalized = _normalize_text(searchable_text)
        searchable_tokens = _tokenize(searchable_text)

        score = difflib.SequenceMatcher(
            None,
            query_normalized,
            searchable_normalized,
        ).ratio()

        if query_tokens:
            token_overlap = len(query_tokens.intersection(searchable_tokens)) / len(query_tokens)
            score += token_overlap * 0.8

        if query_normalized and query_normalized in searchable_normalized:
            score += 0.7

        if document_type and template_detected_type == document_type:
            score += 1.0

        for enum_type, aliases in SUPPORTED_TEMPLATE_ALIASES.items():
            if template_detected_type != enum_type:
                continue

            for alias in aliases:
                alias_normalized = _normalize_text(alias)

                if alias_normalized == query_normalized:
                    score += 1.0
                elif alias_normalized in query_normalized or query_normalized in alias_normalized:
                    score += 0.7

        if score > best_score:
            best_score = score
            best_template = template

    if best_template and best_score >= minimum_score:
        return best_template

    return None


def get_client_folder(client_name: str, document_type: DocumentType) -> str:
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
    folder = get_client_folder(client_name, document_type)

    _, ext = os.path.splitext(original_filename)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
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
    results: List[DocumentInfo] = []

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
                mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).isoformat()

                results.append(
                    DocumentInfo(
                        filename=fname,
                        client_name=client,
                        document_type=doc_type_folder,
                        file_path=fpath,
                        uploaded_at=mtime,
                        size_kb=size_kb,
                    )
                )

    results.sort(key=lambda x: x.uploaded_at or "", reverse=True)
    return results


def search_documents(query: str) -> List[DocumentInfo]:
    q = query.lower().strip()
    all_docs = list_client_documents()

    return [
        d for d in all_docs
        if q in d.filename.lower()
        or q in d.client_name.lower()
        or q in d.document_type.lower()
    ]


def _sanitize_folder_name(name: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*]', "_", name)
    safe = safe.strip(". ")
    return safe or "Unknown"


def _detect_doc_type_from_filename(filename: str) -> Optional[DocumentType]:
    return _detect_supported_template_type(filename)


def detect_doc_type_from_content_or_filename(
    filename: str,
    content_text: str = "",
) -> DocumentType:
    result = _detect_doc_type_from_filename(filename)

    if result:
        return result

    text_upper = content_text.upper()

    keyword_map = {
        DocumentType.FRD: [
            "FUNCTIONAL REQUIREMENT",
            "FUNCTIONAL SPECIFICATION",
            "FRD",
        ],
        DocumentType.HLD: [
            "HIGH LEVEL DESIGN",
            "HIGH-LEVEL DESIGN",
            "HLD",
        ],
        DocumentType.LLD: [
            "LOW LEVEL DESIGN",
            "LOW-LEVEL DESIGN",
            "LLD",
        ],
        DocumentType.DATA_MANAGEMENT_PLAN: [
            "DATA MANAGEMENT PLAN",
            "DMP",
        ],
        DocumentType.SOFTWARE_REQUIREMENTS: [
            "SOFTWARE REQUIREMENTS",
            "SRS",
        ],
    }

    for doc_type, keywords in keyword_map.items():
        if any(keyword in text_upper for keyword in keywords):
            return doc_type

    return DocumentType.OTHER
