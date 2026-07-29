from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.phase_config import PhaseConfig
from app.db.session import get_db
from app.deps import get_client_storage, get_config, get_template_storage
from app.services.document_service import (
    GatingBlocked,
    TemplateNotFound,
    request_template,
    upload_document,
)
from app.storage.base import StorageBackend

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/templates/{doc_type}/download")
def download_template(
    doc_type: str,
    client_name: str,
    db: Session = Depends(get_db),
    template_storage: StorageBackend = Depends(get_template_storage),
    client_storage: StorageBackend = Depends(get_client_storage),
    config: PhaseConfig = Depends(get_config),
):
    try:
        result = request_template(db, client_storage, template_storage, config, doc_type, client_name)
    except GatingBlocked as e:
        raise HTTPException(status_code=409, detail=e.decision.reason) from e
    except TemplateNotFound as e:
        raise HTTPException(status_code=404, detail=f"No master template on file for '{doc_type}'") from e
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
    db: Session = Depends(get_db),
    client_storage: StorageBackend = Depends(get_client_storage),
    config: PhaseConfig = Depends(get_config),
):
    extension = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "bin"
    content = await file.read()

    try:
        result = upload_document(db, client_storage, config, doc_type, client_name, content, extension)
    except GatingBlocked as e:
        raise HTTPException(status_code=409, detail=e.decision.reason) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return {
        "client_name": client_name,
        "phase": result.phase_name,
        "filename": result.filename,
        "stored_path": result.stored_path,
    }
