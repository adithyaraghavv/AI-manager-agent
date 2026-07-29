from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.orchestrator import run_turn
from app.core.phase_config import PhaseConfig
from app.db.session import get_db
from app.deps import get_client_storage, get_config, get_template_storage
from app.storage.base import StorageBackend

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    content: Any


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    messages: list[dict[str, Any]]


@router.post("", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    db: Session = Depends(get_db),
    client_storage: StorageBackend = Depends(get_client_storage),
    template_storage: StorageBackend = Depends(get_template_storage),
    config: PhaseConfig = Depends(get_config),
):
    messages = [m.model_dump() for m in request.messages]
    updated = run_turn(db, client_storage, template_storage, config, messages)
    return ChatResponse(messages=updated)
