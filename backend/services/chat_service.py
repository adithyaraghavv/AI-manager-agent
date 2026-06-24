"""
Chat Response Service
Generates natural-language replies based on detected intent and action results.
"""

import os
import logging
from typing import Optional
from openai import AsyncOpenAI
from models.schemas import IntentType, DocumentType, IntentResult, ChatMessage

logger = logging.getLogger(__name__)


ASSISTANT_PERSONA = """You are DocuBot, a professional and friendly AI assistant for Project Managers.
Your role is to help PMs manage document templates: fetching them, accepting uploads, and organizing them.
Be concise, helpful, and use markdown formatting. Use emojis sparingly for a professional touch.
When templates are fetched successfully, confirm clearly. When clarifying, ask only ONE question at a time."""


async def generate_response(
    user_message: str,
    intent_result: IntentResult,
    action_outcome: Optional[str],
    history: list,
) -> str:
    """
    Generate the chatbot's natural language reply.
    
    Args:
        user_message: What the user said
        intent_result: Classified intent with metadata
        action_outcome: Result description of any action taken (e.g., "Template fetched")
        history: Conversation history for context
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return await _llm_response(user_message, intent_result, action_outcome, history, api_key)
    else:
        return _rule_based_response(intent_result, action_outcome)


async def _llm_response(
    user_message: str,
    intent: IntentResult,
    outcome: Optional[str],
    history: list,
    api_key: str,
) -> str:
    """Generate response using OpenAI."""
    client = AsyncOpenAI(api_key=api_key)

    context = f"""
Detected intent: {intent.intent.value}
Document type: {intent.document_type.value if intent.document_type else 'None'}
Client name: {intent.client_name or 'None'}
Action outcome: {outcome or 'No action taken yet'}
Needs clarification: {intent.needs_clarification}
"""

    messages = [{"role": "system", "content": ASSISTANT_PERSONA}]
    for h in history[-6:]:
        messages.append({"role": h.role, "content": h.content})
    messages.append({
        "role": "user",
        "content": f"[Context: {context}]\n\nUser said: {user_message}"
    })

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=400,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.warning(f"LLM response generation failed: {e}")
        return _rule_based_response(intent, outcome)


def _rule_based_response(
    intent: IntentResult,
    outcome: Optional[str],
) -> str:
    """Deterministic response templates — no API needed."""

    if intent.needs_clarification and intent.clarification_question:
        return intent.clarification_question

    match intent.intent:
        case IntentType.GREETING:
            return (
                "👋 Hello! I'm **DocuBot**, your PM document assistant.\n\n"
                "I can help you:\n"
                "• 📄 **Fetch templates** — SOW, FRD, HLD, LLD, BRD, MSA\n"
                "• 📤 **Upload completed documents** to client folders\n"
                "• 🔍 **Search** your stored documents\n\n"
                "What would you like to do today?"
            )

        case IntentType.FETCH_TEMPLATE:
            if outcome and "not found" in outcome.lower():
                return (
                    f"⚠️ I couldn't find a **{intent.document_type.value if intent.document_type else ''}** "
                    f"template. Please check with your admin to add it to the Templates folder.\n\n"
                    f"Want to see what templates **are** available?"
                )
            doc = intent.document_type.value if intent.document_type else "requested"
            return (
                f"✅ Here's the **{doc}** template! Click the download button below to get your copy.\n\n"
                f"Once you've filled it out, come back and upload the completed document."
            )

        case IntentType.LIST_TEMPLATES:
            return (
                "📋 Here are all the available templates. Click any to download:"
            )

        case IntentType.UPLOAD_DOCUMENT:
            if outcome and "stored" in outcome.lower():
                return (
                    f"✅ Document successfully stored!\n\n"
                    f"{outcome}\n\n"
                    f"Is there anything else you need?"
                )
            return (
                "📤 Great! Please use the upload button below to attach your completed document.\n\n"
                "I'll automatically detect the document type and suggest a storage location."
            )

        case IntentType.STORE_DOCUMENT:
            return f"📁 {outcome or 'Document has been organized into the correct client folder.'}"

        case IntentType.SEARCH_DOCUMENTS:
            return "🔍 Here are the documents matching your search:"

        case IntentType.LIST_CLIENTS:
            return "👥 Here are your active clients with stored documents:"

        case _:
            return (
                "I'm not sure I understood that. Here's what I can help with:\n\n"
                "• Type **'fetch SOW template'** to get a template\n"
                "• Type **'upload document'** to store a completed file\n"
                "• Type **'list templates'** to see all available templates"
            )
