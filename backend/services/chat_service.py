"""
Chat Response Service
Generates natural-language replies based on detected intent and action results.
"""

import os
import logging
from typing import Any, Optional

from openai import AsyncOpenAI

from models.schemas import IntentType, IntentResult

logger = logging.getLogger(__name__)

ASSISTANT_PERSONA = """You are MarBot, a professional and friendly AI assistant for Project Managers at Marlabs.
Your role is to help PMs manage document templates and client project documents.
Be concise, helpful, and use markdown formatting.
When templates are found, confirm clearly. When clarifying, ask only ONE question at a time.
Do not make up template names or client names."""


async def generate_response(
    user_message: str,
    intent_result: IntentResult,
    action_outcome: Optional[str],
    history: list,
) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return await _llm_response(
            user_message, intent_result, action_outcome, history, api_key
        )
    return _rule_based_response(intent_result, action_outcome)


async def _llm_response(
    user_message: str,
    intent: IntentResult,
    outcome: Optional[str],
    history: list,
    api_key: str,
) -> str:
    client = AsyncOpenAI(api_key=api_key)
    context = (
        f"Detected intent: {intent.intent.value}\n"
        f"Document type: {intent.document_type or 'None'}\n"
        f"Client name: {intent.client_name or 'None'}\n"
        f"Matched filename: {intent.matched_filename or 'None'}\n"
        f"Action outcome: {outcome or 'No action taken'}\n"
        f"Needs clarification: {intent.needs_clarification}"
    )
    messages: list[Any] = [{"role": "system", "content": ASSISTANT_PERSONA}]
    _role_map = {"bot": "assistant", "system": "system", "assistant": "assistant", "user": "user"}
    for h in history[-6:]:
        role = (h.get("role") if isinstance(h, dict) else getattr(h, "role", "user")) or "user"
        content = (h.get("content") if isinstance(h, dict) else getattr(h, "content", "")) or ""
        role = _role_map.get(role.lower(), "user")
        if content:
            messages.append({"role": role, "content": content})
    messages.append({
        "role": "user",
        "content": f"[Context:\n{context}]\n\nUser said: {user_message}",
    })
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.6,
            max_tokens=400,
        )
        return response.choices[0].message.content or _rule_based_response(intent, outcome)
    except Exception as e:
        logger.warning("LLM response generation failed: %s", e)
        return _rule_based_response(intent, outcome)


def _rule_based_response(intent: IntentResult, outcome: Optional[str]) -> str:
    match intent.intent:
        case IntentType.GREETING:
            return (
                "Hello! I'm **MarBot**, your PM document assistant.\n\n"
                "I can help you:\n"
                "• **Fetch templates** — FRD, Data Management Plan, HLD, LLD, Software Requirements\n"
                "• **Upload completed documents** to client folders\n"
                "• **List clients** with stored documents\n"
                "• **Get client documents** — browse completed files per client\n"
                "• **Search** your stored documents\n\n"
                "What would you like to do today?"
            )

        case IntentType.FETCH_TEMPLATE:
            if outcome and "needs clarification" in outcome.lower():
                return intent.clarification_question or (
                    "Which template do you need? Available: FRD, HLD, LLD, SRS, Data Management Plan."
                )
            if outcome and "not found" in outcome.lower():
                doc = intent.document_type or "requested"
                return (
                    f"I couldn't find a template matching **{doc}**.\n\n"
                    "Here are the available templates:"
                )
            doc = intent.document_type or intent.matched_filename or "the"
            return (
                f"Here's your **{doc}** template! "
                "Click the download button below to get your copy.\n\n"
                "Once you've filled it out, come back and upload the completed document."
            )

        case IntentType.LIST_TEMPLATES:
            return "Here are all available templates. Click any to download:"

        case IntentType.UPLOAD_DOCUMENT | IntentType.STORE_DOCUMENT:
            if outcome and "stored" in outcome.lower():
                return f"Document stored successfully!\n\n{outcome}\n\nIs there anything else you need?"
            return (
                "Please use the upload button below to attach your completed document.\n\n"
                "I'll store it in the correct client folder."
            )

        case IntentType.LIST_CLIENTS:
            if outcome and "Found 0 clients" in outcome:
                return (
                    "No client folders with stored documents were found yet.\n\n"
                    "Upload completed documents to create client folders."
                )
            return "Here are your active clients with stored documents:"

        case IntentType.FETCH_CLIENT_DOCUMENT:
            client = intent.client_name or "the client"
            doc = intent.document_type or "the document"
            if outcome and "not found" in outcome.lower():
                return (
                    f"I couldn't find client **{client}** in the system.\n\n"
                    "Here are the available clients:"
                )
            if outcome and "no " in outcome.lower() and "found" in outcome.lower():
                return (
                    f"I couldn't find a **{doc}** document for **{client}**.\n\n"
                    f"Here are all documents stored for {client}:"
                )
            if outcome and "found" in outcome.lower():
                return (
                    f"Here's the **{doc}** for **{client}**. "
                    "Click the download button below to get it."
                )
            return (
                f"I need both a client name and a document type. "
                f"Try: *'Give me the LLD doc for {client}'*."
            )

        case IntentType.FETCH_CLIENT_DOCUMENTS:
            client = intent.client_name or "the client"
            if outcome and "not found" in outcome.lower():
                return (
                    f"I couldn't find any documents for client **{client}**.\n\n"
                    "Please check the client name, or upload documents for this client first."
                )
            if outcome and "found 0" in outcome.lower():
                return (
                    f"The folder for **{client}** exists but has no documents yet.\n\n"
                    "Upload completed documents to populate it."
                )
            return f"Here are the completed documents for **{client}**:"

        case IntentType.SEARCH_DOCUMENTS:
            return "Here are the documents matching your search:"

        case IntentType.CLARIFY_INTENT:
            return (
                "I'm not sure what you need. I can:\n"
                "• **Fetch a template** — e.g. 'Give me the FRD template'\n"
                "• **Upload a document** — e.g. 'Upload completed FRD for XYZ'\n"
                "• **List clients** — e.g. 'Show all clients'\n"
                "• **Get client docs** — e.g. 'Show documents for XYZ'\n\n"
                "What would you like to do?"
            )

        case _:
            return (
                "I'm not sure I understood that. Try:\n"
                "• **'fetch FRD template'** to get a template\n"
                "• **'list clients'** to see all clients\n"
                "• **'show documents for XYZ'** to browse a client's files\n"
                "• **'upload document'** to store a completed file"
            )
