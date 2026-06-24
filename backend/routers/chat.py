"""
Chat Router
Core chatbot endpoint: receives messages, detects intent, and responds intelligently.
"""

from fastapi import APIRouter, HTTPException
import uuid
import logging

from models.schemas import ChatRequest, ChatResponse, IntentType, DocumentType
from services.intent_service import detect_intent
from services.storage_service import get_template_path, list_templates, list_client_documents, search_documents
from services.chat_service import generate_response

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main chatbot endpoint.
    
    Flow:
    1. Receive user message + conversation history
    2. Detect intent (LLM or rule-based)
    3. Execute the appropriate action
    4. Generate a natural-language reply
    5. Return response with metadata (download URL, templates, etc.)
    """
    session_id = request.session_id or str(uuid.uuid4())
    message    = request.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # ── Step 1: Detect Intent ─────────────────────────────────────────────────
    intent = await detect_intent(message, request.conversation_history)
    logger.info(f"[{session_id}] Intent: {intent.intent} | Doc: {intent.document_type} | Client: {intent.client_name}")

    # ── Step 2: Execute Action ────────────────────────────────────────────────
    action          = None
    download_url    = None
    available_items = None
    action_outcome  = None

    match intent.intent:

        case IntentType.FETCH_TEMPLATE:
            if intent.needs_clarification:
                action_outcome = "needs clarification"
            elif intent.document_type:
                template_path = get_template_path(intent.document_type)
                if template_path:
                    import os
                    filename     = os.path.basename(template_path)
                    download_url = f"/api/templates/download/{filename}"
                    action       = "download"
                    action_outcome = f"Template '{filename}' is ready for download"
                else:
                    action_outcome = f"Template not found for {intent.document_type.value}"

        case IntentType.LIST_TEMPLATES:
            templates      = list_templates()
            available_items = [t.dict() for t in templates]
            action         = "list_templates"
            action_outcome = f"Found {len(templates)} templates"

        case IntentType.UPLOAD_DOCUMENT:
            # Guide user to upload — actual upload is via POST /api/upload
            action         = "upload_prompt"
            action_outcome = "User should use the upload widget"

        case IntentType.SEARCH_DOCUMENTS:
            # Extract search query from message
            results        = search_documents(message)
            available_items = [d.dict() for d in results]
            action         = "search_results"
            action_outcome = f"Found {len(results)} matching documents"

        case IntentType.LIST_CLIENTS:
            docs           = list_client_documents()
            clients        = list({d.client_name for d in docs})
            available_items = clients
            action_outcome = f"Found {len(clients)} clients"

        case IntentType.GREETING:
            action_outcome = "greeting"

        case _:
            action_outcome = "unknown intent"

    # ── Step 3: Generate Natural-Language Reply ───────────────────────────────
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
