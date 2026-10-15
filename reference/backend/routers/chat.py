"""
Chat Router
Core chatbot endpoint: receives messages, detects intent, and responds.
"""

import uuid
import logging

from fastapi import APIRouter, HTTPException

from models.schemas import ChatRequest, ChatResponse, IntentType
from services.intent_service import detect_intent
from services.storage_service import (
    list_templates,
    list_all_clients,
    find_client_documents,
    find_client_document_by_type,
    search_documents,
    get_template_path,
    find_best_template,
)
from services.chat_service import generate_response

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())
    message = request.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    intent = await detect_intent(message, request.conversation_history)

    logger.info(
        "[%s] Intent=%s | DocType=%s | Client=%s | Filename=%s",
        session_id, intent.intent, intent.document_type,
        intent.client_name, intent.matched_filename,
    )

    action: str | None = None
    download_url: str | None = None
    available_templates = None
    available_clients = None
    action_outcome: str | None = None

    match intent.intent:

        case IntentType.FETCH_TEMPLATE:
            template = None

            # 1. LLM-selected filename (validated against disk)
            if intent.matched_filename:
                path = get_template_path(intent.matched_filename)
                if path:
                    all_tpls = list_templates()
                    template = next(
                        (t for t in all_tpls if t.filename == intent.matched_filename),
                        None,
                    )

            # 2. Fuzzy match against available templates using the full message
            if not template:
                query = (
                    intent.template_name
                    or intent.document_type
                    or intent.document_query
                    or message
                )
                template = find_best_template(query=query, minimum_score=0.3)

            if template:
                download_url = template.download_url
                action = "download"
                action_outcome = f"Template '{template.filename}' ready for download"
            elif intent.needs_clarification and intent.clarification_question:
                # Genuine clarification (query too vague to match anything)
                action_outcome = "needs clarification"
            else:
                all_tpls = list_templates()
                available_templates = [t.model_dump() for t in all_tpls]
                action = "list_templates"
                action_outcome = "No matching template found"

        case IntentType.LIST_TEMPLATES:
            tpls = list_templates()
            available_templates = [t.model_dump() for t in tpls]
            action = "list_templates"
            action_outcome = f"Found {len(tpls)} templates"

        case IntentType.UPLOAD_DOCUMENT | IntentType.STORE_DOCUMENT:
            action = "upload_prompt"
            action_outcome = "User should use the upload widget"

        case IntentType.LIST_CLIENTS:
            clients = list_all_clients()
            available_clients = [c.model_dump() for c in clients]
            action = "list_clients"
            action_outcome = f"Found {len(clients)} clients"

        case IntentType.FETCH_CLIENT_DOCUMENT:
            # Specific doc type for a specific client
            if intent.client_name and intent.document_type:
                doc = find_client_document_by_type(
                    intent.client_name, intent.document_type
                )
                if doc:
                    download_url = doc.download_url
                    action = "download"
                    action_outcome = (
                        f"Found {intent.document_type} for "
                        f"{intent.client_name}: {doc.filename}"
                    )
                else:
                    # Fall back to showing the client's whole folder if it exists
                    client_info = find_client_documents(intent.client_name)
                    if client_info:
                        available_clients = [client_info.model_dump()]
                        action = "client_documents"
                        action_outcome = (
                            f"No {intent.document_type} found for "
                            f"{intent.client_name}. Showing all "
                            f"{client_info.document_count} documents."
                        )
                    else:
                        all_clients = list_all_clients()
                        available_clients = [c.model_dump() for c in all_clients]
                        action = "list_clients"
                        action_outcome = (
                            f"Client '{intent.client_name}' not found."
                        )
            else:
                action_outcome = "needs both client name and document type"

        case IntentType.FETCH_CLIENT_DOCUMENTS:
            if intent.client_name:
                client_info = find_client_documents(intent.client_name)
                if client_info:
                    available_clients = [client_info.model_dump()]
                    action = "client_documents"
                    action_outcome = (
                        f"Found {client_info.document_count} documents "
                        f"for {client_info.client_name}"
                    )
                else:
                    all_clients = list_all_clients()
                    available_clients = [c.model_dump() for c in all_clients]
                    action = "list_clients"
                    action_outcome = (
                        f"Client '{intent.client_name}' not found. "
                        f"Showing {len(all_clients)} available clients."
                    )
            else:
                # No client name — list all
                clients = list_all_clients()
                available_clients = [c.model_dump() for c in clients]
                action = "list_clients"
                action_outcome = f"Found {len(clients)} clients (no specific client specified)"

        case IntentType.SEARCH_DOCUMENTS:
            results = search_documents(message)
            available_templates = [d.model_dump() for d in results]
            action = "search_results"
            action_outcome = f"Found {len(results)} matching documents"

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
        available_templates=available_templates,
        clients=available_clients,
        session_id=session_id,
        success=True,
    )
