"""
Upload Router
Handles file uploads and document storage into client folders.
"""

import os
import uuid
import tempfile
import logging

from fastapi import APIRouter, UploadFile, File, Form, HTTPException

from services.storage_service import (
    store_document,
    detect_doc_type_from_content_or_filename,
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_SIZE_BYTES,
)

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_SIZE_MB = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)


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
    - file          : The document file
    - client_name   : Client or project name (required)
    - document_type : Any descriptive type string (e.g. FRD, HLD, or custom)
    - notes         : Optional notes (not stored)
    """
    effective_client = (client_name or project_name or "").strip()
    if not effective_client:
        raise HTTPException(status_code=400, detail="Client name (or project name) is required.")

    doc_type = document_type.strip()
    if not doc_type:
        raise HTTPException(status_code=400, detail="Document type is required.")

    original_filename = (file.filename or "").strip()
    if not original_filename:
        raise HTTPException(status_code=400, detail="Uploaded file has no filename.")

    _, ext = os.path.splitext(original_filename)
    if ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"File type '{ext}' is not allowed. "
                f"Accepted types: {sorted(ALLOWED_EXTENSIONS)}"
            ),
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    if len(content) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_SIZE_MB} MB.",
        )

    tmp_dir = tempfile.gettempdir()
    tmp_path = os.path.join(tmp_dir, f"upload_{uuid.uuid4().hex}{ext.lower()}")

    try:
        with open(tmp_path, "wb") as f_out:
            f_out.write(content)

        doc_info = store_document(
            source_path=tmp_path,
            client_name=effective_client,
            document_type=doc_type,
            original_filename=original_filename,
        )
    except Exception as exc:
        logger.exception("Failed to store uploaded file")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise HTTPException(status_code=500, detail=f"Failed to store file: {exc}")

    return {
        "success": True,
        "message": f"Document stored successfully for client '{effective_client}'.",
        "document": doc_info.model_dump(),
        "notes": notes,
    }


@router.post("/detect-type")
async def detect_document_type(file: UploadFile = File(...)):
    """
    Auto-detect the document type from filename.
    Useful for pre-filling the document_type field in the UI.
    """
    filename = (file.filename or "").strip()
    detected = detect_doc_type_from_content_or_filename(filename)
    return {
        "filename": filename,
        "detected_type": detected,
        "confidence": "medium",
    }
