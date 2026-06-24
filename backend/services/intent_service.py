"""
Intent Detection Service
Determines what the user wants to do from their message.
Uses OpenAI API with a fallback to rule-based detection.
"""

import os
import re
import json
import logging
from typing import Optional
from openai import AsyncOpenAI
from models.schemas import IntentType, DocumentType, IntentResult

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# Keyword maps for rule-based fallback
# ─────────────────────────────────────────────

FETCH_KEYWORDS   = ["fetch", "get", "download", "give me", "share", "send", "need", "want", "provide"]
UPLOAD_KEYWORDS  = ["upload", "submit", "send", "attach", "here is", "uploading"]
STORE_KEYWORDS   = ["store", "save", "file", "put", "organize", "archive"]
LIST_KEYWORDS    = ["list", "show", "all", "available", "what templates", "which templates"]
SEARCH_KEYWORDS  = ["search", "find", "locate", "look for"]
GREET_KEYWORDS   = ["hello", "hi", "hey", "good morning", "good afternoon", "howdy"]

DOC_TYPE_KEYWORDS: dict[DocumentType, list[str]] = {
    DocumentType.SOW: ["sow", "statement of work", "scope of work"],
    DocumentType.FRD: ["frd", "functional requirement", "functional spec"],
    DocumentType.HLD: ["hld", "high level design", "high-level design"],
    DocumentType.LLD: ["lld", "low level design", "low-level design"],
    DocumentType.BRD: ["brd", "business requirement", "business spec"],
    DocumentType.MSA: ["msa", "master service", "service agreement"],
}


# ─────────────────────────────────────────────
# OpenAI-based Intent Detection
# ─────────────────────────────────────────────

SYSTEM_PROMPT = """You are an intent classifier for a Project Management Document Assistant.

Classify the user's message into exactly one intent from this list:
- FETCH_TEMPLATE   : user wants to download a document template
- UPLOAD_DOCUMENT  : user is uploading or submitting a completed document
- STORE_DOCUMENT   : user wants to store/save a document for a client
- LIST_TEMPLATES   : user wants to see available templates
- LIST_CLIENTS     : user wants to see existing clients/projects
- SEARCH_DOCUMENTS : user wants to search stored documents
- GREETING         : casual greeting or small talk
- CLARIFY_INTENT   : intent is unclear, needs more info
- UNKNOWN          : cannot determine intent

Also extract:
- document_type: one of SOW, FRD, HLD, LLD, BRD, MSA, OTHER, or null
- client_name: the client/company name mentioned, or null
- needs_clarification: true if more info is needed
- clarification_question: what to ask the user if needs_clarification is true

Respond ONLY with valid JSON matching this schema:
{
  "intent": "FETCH_TEMPLATE",
  "document_type": "SOW",
  "client_name": "Acme Corp",
  "confidence": 0.95,
  "needs_clarification": false,
  "clarification_question": null
}"""


async def detect_intent_llm(
    message: str,
    history: list,
    client: AsyncOpenAI
) -> IntentResult:
    """
    Use OpenAI to classify intent with high accuracy.
    Sends conversation history for better context.
    """
    # Build messages array with history (last 6 turns max)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history[-6:]:
        messages.append({"role": h.role, "content": h.content})
    messages.append({"role": "user", "content": message})

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0,        # Deterministic classification
            response_format={"type": "json_object"},
            max_tokens=300,
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)

        # Map raw strings to Enums safely
        intent = IntentType(data.get("intent", "UNKNOWN"))
        doc_type_str = data.get("document_type")
        doc_type = None
        if doc_type_str and doc_type_str != "null":
            try:
                doc_type = DocumentType(doc_type_str)
            except ValueError:
                doc_type = None

        return IntentResult(
            intent=intent,
            document_type=doc_type,
            client_name=data.get("client_name"),
            confidence=float(data.get("confidence", 0.8)),
            needs_clarification=bool(data.get("needs_clarification", False)),
            clarification_question=data.get("clarification_question"),
        )

    except Exception as e:
        logger.warning(f"LLM intent detection failed: {e}. Falling back to rule-based.")
        return detect_intent_rules(message)


def detect_intent_rules(message: str) -> IntentResult:
    """
    Rule-based fallback intent detection.
    Works without OpenAI API; used when LLM is unavailable.
    """
    msg = message.lower().strip()

    # Detect document type first
    detected_doc_type: Optional[DocumentType] = None
    for doc_type, keywords in DOC_TYPE_KEYWORDS.items():
        if any(kw in msg for kw in keywords):
            detected_doc_type = doc_type
            break

    # Extract client name heuristic: "for <Client>" or "client: <name>"
    client_name = None
    client_match = re.search(r"(?:for|client[:\s]+|project[:\s]+)\s+([A-Z][a-zA-Z\s&]+?)(?:\s+(?:template|document|file|$))", message)
    if client_match:
        client_name = client_match.group(1).strip()

    # Detect greeting
    if any(kw in msg for kw in GREET_KEYWORDS):
        return IntentResult(
            intent=IntentType.GREETING,
            confidence=0.95,
        )

    # Detect list request
    if any(kw in msg for kw in LIST_KEYWORDS):
        return IntentResult(
            intent=IntentType.LIST_TEMPLATES,
            confidence=0.85,
        )

    # Detect search
    if any(kw in msg for kw in SEARCH_KEYWORDS):
        return IntentResult(
            intent=IntentType.SEARCH_DOCUMENTS,
            confidence=0.85,
        )

    # Detect upload
    if any(kw in msg for kw in UPLOAD_KEYWORDS):
        needs_clarification = not client_name or not detected_doc_type
        return IntentResult(
            intent=IntentType.UPLOAD_DOCUMENT,
            document_type=detected_doc_type,
            client_name=client_name,
            confidence=0.8,
            needs_clarification=needs_clarification,
            clarification_question=(
                "Sure! To store this correctly — could you tell me the client name and document type?"
                if needs_clarification else None
            ),
        )

    # Detect fetch/download
    if any(kw in msg for kw in FETCH_KEYWORDS):
        if detected_doc_type:
            return IntentResult(
                intent=IntentType.FETCH_TEMPLATE,
                document_type=detected_doc_type,
                client_name=client_name,
                confidence=0.9,
            )
        else:
            return IntentResult(
                intent=IntentType.FETCH_TEMPLATE,
                confidence=0.65,
                needs_clarification=True,
                clarification_question=(
                    "I'd be happy to fetch a template! Which type do you need?\n"
                    "Available: **SOW**, **FRD**, **HLD**, **LLD**, **BRD**, **MSA**"
                ),
            )

    # Ambiguous — ask for clarification
    return IntentResult(
        intent=IntentType.CLARIFY_INTENT,
        confidence=0.3,
        needs_clarification=True,
        clarification_question=(
            "I'm not quite sure what you need. I can help you:\n"
            "• 📄 **Fetch a template** (SOW, FRD, HLD, LLD, etc.)\n"
            "• 📤 **Upload a completed document**\n"
            "• 🔍 **Search stored documents**\n\n"
            "What would you like to do?"
        ),
    )


# ─────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────

async def detect_intent(
    message: str,
    history: list,
) -> IntentResult:
    """
    Primary intent detection function.
    Tries OpenAI first, falls back to rule-based.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        client = AsyncOpenAI(api_key=api_key)
        return await detect_intent_llm(message, history, client)
    else:
        # Fallback: rule-based (works without OpenAI key)
        logger.info("No OPENAI_API_KEY found — using rule-based intent detection")
        return detect_intent_rules(message)
