"""
Templates Router
Endpoints for listing and downloading document templates.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os

from services.storage_service import (
    get_template_path,
    list_templates,
    TEMPLATES_DIR,
)
from models.schemas import DocumentType

router = APIRouter()


@router.get("/")
def get_all_templates():
    """List all available templates with metadata."""
    templates = list_templates()
    return {"templates": [t.dict() for t in templates], "count": len(templates)}


@router.get("/{doc_type}")
def get_template(doc_type: str):
    """
    Get metadata for a specific template type.
    Example: GET /api/templates/SOW
    """
    try:
        doc_enum = DocumentType(doc_type.upper())
    except ValueError:
        valid = [d.value for d in DocumentType if d != DocumentType.OTHER]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document type '{doc_type}'. Valid types: {valid}"
        )

    path = get_template_path(doc_enum)
    if not path:
        raise HTTPException(
            status_code=404,
            detail=f"No template found for {doc_enum.value}. Please contact your admin."
        )

    filename = os.path.basename(path)
    size_kb  = round(os.path.getsize(path) / 1024, 2)
    return {
        "document_type": doc_enum.value,
        "filename": filename,
        "download_url": f"/api/templates/download/{filename}",
        "size_kb": size_kb,
        "found": True,
    }


@router.get("/download/{filename}")
def download_template(filename: str):
    """
    Stream a template file for download.
    Example: GET /api/templates/download/sow_template.docx
    """
    # Security: prevent directory traversal
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(TEMPLATES_DIR, safe_filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File '{safe_filename}' not found")

    return FileResponse(
        path=file_path,
        filename=safe_filename,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
