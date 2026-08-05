"""
Templates Router
Endpoints for listing and downloading document templates (dynamically discovered).
"""

import os
import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from services.storage_service import (
    list_templates,
    get_template_path,
    find_best_template,
    TEMPLATES_DIR,
)

router = APIRouter()


@router.get("/download/{filename}")
def download_template(filename: str):
    """
    Stream a template file for download.
    Example: GET /api/templates/download/frd_template.docx
    """
    safe_filename = os.path.basename(filename)
    file_path = os.path.join(TEMPLATES_DIR, safe_filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Template file '{safe_filename}' not found.")

    media_type, _ = mimetypes.guess_type(file_path)
    media_type = media_type or "application/octet-stream"

    return FileResponse(
        path=file_path,
        filename=safe_filename,
        media_type=media_type,
    )


@router.get("/")
def get_all_templates():
    """List all available templates with metadata."""
    templates = list_templates()
    return {
        "success": True,
        "templates": [t.model_dump() for t in templates],
        "count": len(templates),
    }


@router.get("/{doc_type}")
def get_template_by_type(doc_type: str):
    """
    Get metadata for a template matching a type/name query.
    Example: GET /api/templates/FRD
    Example: GET /api/templates/High%20Level%20Design
    """
    if not os.path.exists(TEMPLATES_DIR):
        raise HTTPException(
            status_code=503,
            detail="Templates directory not found. Please contact your administrator.",
        )

    template = find_best_template(query=doc_type, minimum_score=0.2)

    if not template:
        available = list_templates()
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"No template found matching '{doc_type}'.",
                "available_templates": [t.model_dump() for t in available],
            },
        )

    return {
        "success": True,
        "document_type": template.document_type,
        "filename": template.filename,
        "download_url": template.download_url,
        "size_kb": template.size_kb,
        "found": True,
    }
