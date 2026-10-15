"""
Documents Router
Endpoints for browsing, searching, and downloading stored client documents.
"""

import os
import mimetypes

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from services.storage_service import (
    list_all_clients,
    list_client_documents,
    search_documents,
    get_client_file_path,
    CLIENTS_DIR,
    PROJECT_ROOT,
)

router = APIRouter()


@router.get("/")
def list_all_documents(client: str = Query(default=None, description="Filter by client name")):
    """List all stored documents, optionally filtered by client."""
    docs = list_client_documents(client_name=client)
    return {
        "documents": [d.model_dump() for d in docs],
        "count": len(docs),
        "filter_client": client,
    }


@router.get("/clients")
def list_clients_endpoint():
    """List all clients with stored documents."""
    clients = list_all_clients()
    return {
        "success": True,
        "clients": [c.model_dump() for c in clients],
        "count": len(clients),
        "message": (
            "Here are your active clients with stored documents."
            if clients
            else "No client folders with stored documents were found yet."
        ),
    }


@router.get("/search")
def search(q: str = Query(..., min_length=1, description="Search query")):
    """Search documents by filename, client name, or document type."""
    results = search_documents(q)
    return {
        "query": q,
        "results": [d.model_dump() for d in results],
        "count": len(results),
    }


@router.get("/client-file")
def download_client_file(
    path: str = Query(..., description="Relative path from project root (forward slashes)")
):
    """
    Download a stored client document by its relative path.
    Path is validated to be within an allowed client directory.
    """
    abs_path = get_client_file_path(path)

    if abs_path is None:
        raise HTTPException(
            status_code=404,
            detail="File not found or access denied. The file may have been moved or you do not have permission.",
        )

    filename = os.path.basename(abs_path)
    media_type, _ = mimetypes.guess_type(abs_path)
    media_type = media_type or "application/octet-stream"

    return FileResponse(
        path=abs_path,
        filename=filename,
        media_type=media_type,
    )


@router.get("/download")
def download_document_legacy(
    file_path: str = Query(..., description="Absolute path of stored document")
):
    """
    Legacy download endpoint. Validates path is within an allowed client directory.
    Prefer /client-file for new usage.
    """
    abs_path = os.path.abspath(file_path)
    project_root_abs = os.path.abspath(PROJECT_ROOT)

    if not abs_path.startswith(project_root_abs):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="File not found")

    filename = os.path.basename(abs_path)
    media_type, _ = mimetypes.guess_type(abs_path)
    media_type = media_type or "application/octet-stream"

    return FileResponse(path=abs_path, filename=filename, media_type=media_type)
