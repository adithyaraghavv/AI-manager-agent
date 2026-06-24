"""
Upload Router
Handles file uploads and document storage into client folders.
"""

import os
import uuid
import tempfile
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from models.schemas import DocumentType
from services.storage_service import (
    store_document,
    detect_doc_type_from_content_or_filename,
)

router = APIRouter()

# Allowed file extensions
ALLOWED_EXTENSIONS = {".docx", ".pdf", ".xlsx", ".pptx", ".doc", ".txt"}


@router.post("/")
async def upload_document(
    file: UploadFile = File(...),
    client_name: str = Form(...),
    document_type: str = Form(...),
    notes: str = Form(default=""),
):
    """
    Upload a completed document and store it in the correct client folder.

    Body (multipart/form-data):
    - file: The document file
    - client_name: Client/project name (e.g., "Acme Corp")
    - document_type: SOW, FRD, HLD, LLD, BRD, MSA, or OTHER
    """
    # ── Validate file extension
    _, ext = os.path.splitext(file.filename or "")
    if ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Accepted: {list(ALLOWED_EXTENSIONS)}"
        )

    # ── Validate document type
    try:
        doc_enum = DocumentType(document_type.upper())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document type '{document_type}'."
        )

    # ── Validate client name
    client_name = client_name.strip()
    if not client_name:
        raise HTTPException(status_code=400, detail="Client name cannot be empty.")

    # ── Save to a temp file first
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Write to temp location
    tmp_dir  = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, f"upload_{uuid.uuid4().hex}{ext}")
    with open(tmp_path, "wb") as f_out:
        f_out.write(content)

    # ── Store the document
    try:
        doc_info = store_document(
            source_path=tmp_path,
            client_name=client_name,
            document_type=doc_enum,
            original_filename=file.filename or f"document{ext}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to store file: {str(e)}")

    return {
        "success": True,
        "message": f"Document stored successfully for client '{client_name}'",
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
        "confidence": "high" if detected else "low",
    }
