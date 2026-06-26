"""
Chat Router
Core chatbot endpoint: receives messages, detects intent, and responds intelligently.
"""

import uuid
import logging

from fastapi import APIRouter, HTTPException

from models.schemas import ChatRequest, ChatResponse, IntentType
from services.intent_service import detect_intent
from services.storage_service import (
    list_templates,
    list_client_documents,
    search_documents,
    find_best_template,
)
from services.chat_service import generate_response

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chatbot endpoint.
    """

    session_id = request.session_id or str(uuid.uuid4())
    message = request.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    intent = await detect_intent(message, request.conversation_history)

    logger.info(
        "[%s] Intent: %s | Doc: %s | Client: %s",
        session_id,
        intent.intent,
        intent.document_type,
        intent.client_name,
    )

    action = None
    download_url = None
    available_items = None
    action_outcome = None

    match intent.intent:
        case IntentType.FETCH_TEMPLATE:
            if intent.needs_clarification:
                action_outcome = "needs clarification"
            else:
                template = find_best_template(
                    query=getattr(intent, "template_name", None) or message,
                    document_type=intent.document_type,
                    minimum_score=0.35,
                )

                if template:
                    download_url = template.download_url
                    action = "download"
                    action_outcome = f"Template '{template.filename}' ready"
                else:
                    templates = list_templates()
                    available_items = [t.dict() for t in templates]
                    action = "list_templates"
                    action_outcome = "No matching template found"

        case IntentType.LIST_TEMPLATES:
            templates = list_templates()
            available_items = [t.dict() for t in templates]
            action = "list_templates"
            action_outcome = f"Found {len(templates)} templates"

        case IntentType.UPLOAD_DOCUMENT:
            action = "upload_prompt"
            action_outcome = "User should use the upload widget"

        case IntentType.STORE_DOCUMENT:
            action = "upload_prompt"
            action_outcome = "User should use the upload widget"

        case IntentType.SEARCH_DOCUMENTS:
            results = search_documents(message)
            available_items = [d.dict() for d in results]
            action = "search_results"
            action_outcome = f"Found {len(results)} matching documents"

        case IntentType.LIST_CLIENTS:
            docs = list_client_documents()
            clients = sorted(list({d.client_name for d in docs}))
            available_items = clients
            action = "list_clients"
            action_outcome = f"Found {len(clients)} clients"

        case IntentType.GREETING:
            action_outcome = "greeting"

        case IntentType.CLARIFY_INTENT:
            action_outcome = "needs clarification"

        case _:
            action_outcome = "unknown intent"

    bot_message = await generate_response(
        user_message=message,
        intent_result=intent,
        action_outcome=action_outcome,
        history=request.conversation_history,
    )

    return ChatResponse(
        message=bot_message,
        intent=intent.intent,
        document_type=intent.document_type,
        client_name=intent.client_name,
        action=action,
        download_url=download_url,
        available_templates=available_items,
        session_id=session_id,
    )