from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.agent.orchestrator import run_turn
from app.core.phase_config import PhaseConfig
from app.db.rest_client import SupabaseRestClient
from app.deps import get_client_storage, get_config, get_rest_client, get_template_storage
from app.storage.base import StorageBackend

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessage(BaseModel):
    """Round-trips whatever the frontend sends back verbatim.

    OpenAI requires role="tool" messages to carry tool_call_id, and
    role="assistant" tool-call messages to carry tool_calls — both of which
    are only present on some messages. `extra="allow"` preserves them
    instead of silently stripping them, which previously broke the second
    turn of any conversation that involved a tool call.
    """

    model_config = ConfigDict(extra="allow")

    role: str
    content: Any = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    messages: list[dict[str, Any]]


@router.post("", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    rest: SupabaseRestClient = Depends(get_rest_client),
    client_storage: StorageBackend = Depends(get_client_storage),
    template_storage: StorageBackend = Depends(get_template_storage),
    config: PhaseConfig = Depends(get_config),
):
    messages = [m.model_dump() for m in request.messages]
    updated = run_turn(rest, client_storage, template_storage, config, messages)
    return ChatResponse(messages=updated)
