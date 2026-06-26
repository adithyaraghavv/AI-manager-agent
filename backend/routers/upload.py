"""
Upload Router
Handles file uploads and document storage into client folders.
"""

import os
import uuid
import tempfile

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from models.schemas import DocumentType, normalize_document_type
from services.storage_service import (
    store_document,
    detect_doc_type_from_content_or_filename,
)

router = APIRouter()

ALLOWED_EXTENSIONS = {".docx", ".pdf", ".xlsx", ".pptx", ".doc", ".txt"}


@router.post("/")
async def upload_document(
    file: UploadFile = File(...),
    client_name: str | None = Form(default=None),
    project_name: str | None = Form(default=None),
    document_type: str = Form(...),
    notes: str = Form(default=""),
):
    """
    Upload a completed document and store it in the correct client folder.

    Body (multipart/form-data):
    - file: The document file
    - client_name / project_name: Client/project name
    - document_type: FRD, DATA_MANAGEMENT_PLAN, HLD, LLD, SOFTWARE_REQUIREMENTS, or OTHER
    """

    effective_client_name = (client_name or project_name or "").strip()
    if not effective_client_name:
        raise HTTPException(status_code=400, detail="Client name cannot be empty.")

    _, ext = os.path.splitext(file.filename or "")
    if ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Accepted: {sorted(ALLOWED_EXTENSIONS)}",
        )

    doc_enum = normalize_document_type(document_type)
    if doc_enum is None:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document type '{document_type}'.",
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    tmp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, f"upload_{uuid.uuid4().hex}{ext}")

    with open(tmp_path, "wb") as f_out:
        f_out.write(content)

    try:
        doc_info = store_document(
            source_path=tmp_path,
            client_name=effective_client_name,
            document_type=doc_enum,
            original_filename=file.filename or f"document{ext}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store file: {str(e)}")

    return {
        "success": True,
        "message": f"Document stored successfully for client '{effective_client_name}'",
        "document": doc_info.dict(),
        "notes": notes,
    }


@router.post("/detect-type")
async def detect_document_type(file: UploadFile = File(...)):
    """
    Auto-detect the document type from filename (and optionally content).
    Useful for pre-filling the document_type field in the UI.
    """
    filename = file.filename or ""
    detected = detect_doc_type_from_content_or_filename(filename)

    return {
        "filename": filename,
        "detected_type": detected.value if detected else None,
        "confidence": "high" if detected and detected != DocumentType.OTHER else "low",
    }