"""
Documents Router
Endpoints for browsing and searching stored client documents.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
import os

from services.storage_service import (
    list_client_documents,
    search_documents,
    CLIENTS_DIR,
)

router = APIRouter()


@router.get("/")
def list_all_documents(client: str = Query(default=None, description="Filter by client name")):
    """List all stored documents, optionally filtered by client."""
    docs = list_client_documents(client_name=client)
    return {
        "documents": [d.dict() for d in docs],
        "count": len(docs),
        "filter_client": client,
    }


@router.get("/clients")
def list_clients():
    """List all clients that have stored documents."""
    if not os.path.exists(CLIENTS_DIR):
        return {"clients": []}

    clients = [
        name for name in os.listdir(CLIENTS_DIR)
        if os.path.isdir(os.path.join(CLIENTS_DIR, name))
    ]
    return {"clients": sorted(clients), "count": len(clients)}


@router.get("/search")
def search(q: str = Query(..., min_length=1, description="Search query")):
    """Search documents by filename, client name, or document type."""
    results = search_documents(q)
    return {
        "query": q,
        "results": [d.dict() for d in results],
        "count": len(results),
    }


@router.get("/download")
def download_document(file_path: str = Query(..., description="Full path of the stored document")):
    """
    Download a specific stored document.
    NOTE: In production, use signed URLs or access control here.
    """
    # Security: ensure path is within Clients directory
    abs_path = os.path.abspath(file_path)
    abs_clients = os.path.abspath(CLIENTS_DIR)

    if not abs_path.startswith(abs_clients):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="File not found")

    filename = os.path.basename(abs_path)
    return FileResponse(path=abs_path, filename=filename)
