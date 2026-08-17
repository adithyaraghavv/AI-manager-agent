from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response

from app.core.phase_config import PhaseConfig
from app.db.rest_client import SupabaseRestClient
from app.deps import get_client_storage, get_config, get_rest_client, get_template_storage
from app.core.upload_validation import InvalidUpload
from app.services.client_service import delete_client, find_client
from app.services.document_service import (
    ClientDocumentNotFound,
    GatingBlocked,
    TemplateFileMissing,
    TemplateNotFound,
    get_document_version,
    get_stored_document,
    list_document_versions,
    request_template,
    restore_document_version,
    upload_document,
)
from app.services.search_service import search_documents
from app.services.version_service import VersionNumberConflict
from app.storage.base import StorageBackend

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/phases")
def list_phases(config: PhaseConfig = Depends(get_config)):
    """Plain lookup of phases/required documents for the frontend — e.g. to populate a
    document-type picker with exact valid values instead of asking a PM to type one from
    memory, which is guaranteed to drift from the config eventually."""
    return {
        "phases": [
            {"sequence": p.sequence, "name": p.name, "required_documents": list(p.required_documents)}
            for p in config.phases
        ]
    }


@router.get("/templates/{doc_type}/download")
def download_template(
    doc_type: str,
    client_name: str,
    rest: SupabaseRestClient = Depends(get_rest_client),
    template_storage: StorageBackend = Depends(get_template_storage),
    client_storage: StorageBackend = Depends(get_client_storage),
    config: PhaseConfig = Depends(get_config),
):
    try:
        result = request_template(rest, client_storage, template_storage, config, doc_type, client_name)
    except GatingBlocked as e:
        raise HTTPException(status_code=409, detail=e.decision.reason) from e
    except TemplateNotFound as e:
        raise HTTPException(status_code=404, detail=f"No master template on file for '{doc_type}'") from e
    except TemplateFileMissing as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return Response(
        content=result.content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.post("/clients/{client_name}/documents")
async def upload_client_document(
    client_name: str,
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    uploaded_by: str | None = Form(None),
    comment: str | None = Form(None),
    rest: SupabaseRestClient = Depends(get_rest_client),
    client_storage: StorageBackend = Depends(get_client_storage),
    config: PhaseConfig = Depends(get_config),
):
    extension = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "bin"
    content = await file.read()

    try:
        result = upload_document(
            rest, client_storage, config, doc_type, client_name, content, extension,
            uploaded_by=uploaded_by, comment=comment,
        )
    except InvalidUpload as e:
        status = 413 if "too large" in e.message.lower() else 400
        raise HTTPException(status_code=status, detail=e.message) from e
    except GatingBlocked as e:
        raise HTTPException(status_code=409, detail=e.decision.reason) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except VersionNumberConflict as e:
        # Only reachable if every retry inside upload_document also lost the
        # race — extremely unlikely, but a real conflict, not a bug, so 409
        # rather than a raw 500.
        raise HTTPException(status_code=409, detail=str(e)) from e

    return {
        "client_name": client_name,
        "phase": result.phase_name,
        "filename": result.filename,
        "stored_path": result.stored_path,
        "version_number": result.version_number,
    }


@router.get("/documents/search")
def search_documents_route(
    q: str = Query(..., min_length=1, description="Search by client name, document type, or filename"),
    rest: SupabaseRestClient = Depends(get_rest_client),
):
    results = search_documents(rest, q)
    return {
        "query": q,
        "count": len(results),
        "results": [
            {
                "client_name": r.client_name,
                "doc_type": r.doc_type,
                "filename": r.filename,
                "phase_name": r.phase_name,
                "version_count": r.version_count,
                "download_url": f"/api/clients/{r.client_name}/documents/{r.doc_type}/download",
            }
            for r in results
        ],
    }


@router.get("/clients/{client_name}/documents/{doc_type}/download")
def download_client_document(
    client_name: str,
    doc_type: str,
    rest: SupabaseRestClient = Depends(get_rest_client),
    client_storage: StorageBackend = Depends(get_client_storage),
):
    try:
        result = get_stored_document(rest, client_storage, client_name, doc_type)
    except ClientDocumentNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return Response(
        content=result.content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.get("/clients/{client_name}/documents/{doc_type}/versions")
def list_document_versions_route(
    client_name: str,
    doc_type: str,
    rest: SupabaseRestClient = Depends(get_rest_client),
):
    try:
        versions = list_document_versions(rest, client_name, doc_type)
    except ClientDocumentNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return {
        "client_name": client_name,
        "doc_type": doc_type,
        "versions": [
            {
                "version_number": v.version_number,
                "filename": v.filename,
                "uploaded_by": v.uploaded_by,
                "comment": v.comment,
                "uploaded_at": v.uploaded_at,
                "download_url": f"/api/clients/{client_name}/documents/{doc_type}/versions/{v.version_number}/download",
            }
            for v in versions
        ],
    }


@router.get("/clients/{client_name}/documents/{doc_type}/versions/{version_number}/download")
def download_document_version_route(
    client_name: str,
    doc_type: str,
    version_number: int,
    rest: SupabaseRestClient = Depends(get_rest_client),
    client_storage: StorageBackend = Depends(get_client_storage),
):
    try:
        result = get_document_version(rest, client_storage, client_name, doc_type, version_number)
    except ClientDocumentNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return Response(
        content=result.content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.post("/clients/{client_name}/documents/{doc_type}/versions/{version_number}/restore")
def restore_document_version_route(
    client_name: str,
    doc_type: str,
    version_number: int,
    uploaded_by: str | None = Form(None),
    comment: str | None = Form(None),
    rest: SupabaseRestClient = Depends(get_rest_client),
    client_storage: StorageBackend = Depends(get_client_storage),
):
    """Makes an earlier version current again by copying its content forward
    as a brand new version — never deletes or overwrites any existing
    version, including the one being replaced as "current"."""
    try:
        result = restore_document_version(
            rest, client_storage, client_name, doc_type, version_number, uploaded_by=uploaded_by, comment=comment
        )
    except ClientDocumentNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    return {
        "client_name": client_name,
        "doc_type": doc_type,
        "restored_from_version": version_number,
        "new_version_number": result.version_number,
        "filename": result.filename,
    }


@router.delete("/clients/{client_name}")
def delete_client_route(
    client_name: str,
    rest: SupabaseRestClient = Depends(get_rest_client),
    client_storage: StorageBackend = Depends(get_client_storage),
):
    """Soft-deletes a client (see client_service.delete_client — hidden everywhere,
    recoverable until the retention window's cleanup purges it). This is the ONLY
    path that actually performs a deletion — the chat agent's propose_delete_client
    tool never calls this itself, it only surfaces a confirm card in the UI that
    hits this endpoint on click."""
    client = find_client(rest, client_name)
    if client is None:
        raise HTTPException(status_code=404, detail=f"No client named '{client_name}'")

    delete_client(rest, client_storage, client)
    return {"deleted": True, "client_name": client_name}
