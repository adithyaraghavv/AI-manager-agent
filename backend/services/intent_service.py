"""
Intent Detection Service
Determines what the user wants to",Determines what the user wants to do from their message.
"""

import os
import re
import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from models.schemas import (
    IntentType,
    DocumentType,
    IntentResult,
    normalize_document_type,
)

logger = logging.getLogger(__name__)


FETCH_KEYWORDS = [
    "fetch",
    "get",
    "download",
    "give me",

    "send me",
    "provide",
    "template",
]

UPLOAD_KEYWORDS = [
    "upload",
    "submit",
    "attach",
    "here is",
    "i am uploading",
    "uploading",
]

STORE_KEYWORDS = [
    "store",
    "save",
    "archive",
    "organize",
    "keep this",
]

LIST_TEMPLATE_KEYWORDS = [
    "list templates",
    "show templates",
    "available templates",
    "what templates do you have",
    "which templates are available",
    "template list",
]

LIST_CLIENTS_KEYWORDS = [
    "list clients",
    "show clients",
    "existing clients",
    "available clients",
    "list projects",
    "show projects",
    "existing projects",
]

SEARCH_KEYWORDS = [
    "search",
    "find",
    "locate",
    "look for",
    "search documents",
    "find document",
    "find file",
]

GREET_KEYWORDS = [
    "hello",
    "hi",
    "hey",
    "good morning",
    "good afternoon",
    "howdy",
]


DOC_TYPE_KEYWORDS: dict[DocumentType, list[str]] = {
    DocumentType.FRD: [
        "frd",
        "functional requirement",
        "functional requirements",
        "functional requirements document",
        "functional spec",
        "functional specification",
    ],
    DocumentType.DATA_MANAGEMENT_PLAN: [
        "data management plan",
        "data plan",
        "dmp",
        "data management",
    ],
    DocumentType.HLD: [
        "hld",
        "high level design",
        "high-level design",
        "architecture document",
        "architecture doc",
        "solution design",
    ],
    DocumentType.LLD: [
        "lld",
        "low level design",
        "low-level design",
        "detailed design",
        "technical design",
    ],
    DocumentType.SOFTWARE_REQUIREMENTS: [
        "software requirements",
        "software requirements template",
        "software requirement",
        "requirements document",
        "requirement document",
        "requirements doc",
        "srs",
        "specification document",
    ],
}


SYSTEM_PROMPT = """
You are an intent classifier for a Project Management Document Assistant.

Classify the user's message into exactly one intent from this list:
- FETCH_TEMPLATE
- UPLOAD_DOCUMENT
- STORE_DOCUMENT
- LIST_TEMPLATES
- LIST_CLIENTS
- SEARCH_DOCUMENTS
- GREETING
- CLARIFY_INTENT
- UNKNOWN

Supported document types:
- FRD
- DATA_MANAGEMENT_PLAN
- HLD
- LLD
- SOFTWARE_REQUIREMENTS
- OTHER
- null

Also extract:
- document_type
- client_name
- needs_clarification
- clarification_question

Rules:
- If the user clearly mentions a supported document type like "FRD", "HLD", "LLD", "data management plan", "software requirements", or similar variations, map it correctly.
- If the user message is vague but still looks like they want a template, for example just a doc type name, classify as FETCH_TEMPLATE if that is the most likely intent.
- If more information is required, set needs_clarification=true and provide one short helpful question.
- Respond ONLY with valid JSON matching this schema:

{
  "intent": "FETCH_TEMPLATE",
  "document_type": "FRD",
  "client_name": "Acme Corp",
  "confidence": 0.95,
  "needs_clarification": false,
  "clarification_question": null
}
""".strip()


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("/", " ")
    text = text.replace("-", " ")
    text = re.sub(r"[^\w\s&.]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _contains_keyword(message: str, keywords: list[str]) -> bool:
    normalized = _normalize_text(message)

    for keyword in keywords:
        keyword_normalized = _normalize_text(keyword)
        if keyword_normalized and keyword_normalized in normalized:
            return True

    return False


def _is_greeting(message: str) -> bool:
    normalized = _normalize_text(message)

    return any(
        re.search(rf"\b{re.escape(_normalize_text(keyword))}\b", normalized)
        for keyword in GREET_KEYWORDS
    )


def _detect_document_type(message: str) -> Optional[DocumentType]:
    normalized = _normalize_text(message)

    for document_type, keywords in DOC_TYPE_KEYWORDS.items():
        for keyword in keywords:
            if _normalize_text(keyword) in normalized:
                return document_type

    return None


def _extract_client_name(message: str) -> Optional[str]:
    patterns = [
        r"(?:for|client|project)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9&.\- ]{1,80}?)(?=\s+(?:template|document|doc|file|please|thanks)\b|$)",
        r"(?:client name|project name)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9&.\- ]{1,80})",
    ]

    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)

        if match:
            client_name = match.group(1).strip(" .,-")
            if client_name:
                return client_name

    return None


def _safe_intent(value: Optional[str]) -> IntentType:
    if not value:
        return IntentType.UNKNOWN

    cleaned = str(value).strip().upper()

    try:
        return IntentType(cleaned)
    except Exception:
        return IntentType.UNKNOWN


def _safe_doc_type(value: Optional[str]) -> Optional[DocumentType]:
    return normalize_document_type(value)


def _safe_confidence(value) -> float:
    try:
        confidence = float(value)
    except Exception:
        confidence = 0.8

    return max(0.0, min(1.0, confidence))


def _build_messages(message: str, history: list) -> list[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    for item in history[-6:]:
        if isinstance(item, dict):
            role = item.get("role", "user")
            content = item.get("content", "")
        else:
            role = getattr(item, "role", "user")
            content = getattr(item, "content", "")

        if role in {"system", "user", "assistant"} and content:
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": message})
    return messages


async def detect_intent_llm(
    message: str,
    history: list,
    client: AsyncOpenAI,
) -> IntentResult:
    messages = _build_messages(message, history)

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=300,
        )

        raw = response.choices[0].message.content
        data = json.loads(raw)

        return IntentResult(
            intent=_safe_intent(data.get("intent")),
            document_type=_safe_doc_type(data.get("document_type")),
            client_name=data.get("client_name"),
            confidence=_safe_confidence(data.get("confidence", 0.8)),
            needs_clarification=bool(data.get("needs_clarification", False)),
            clarification_question=data.get("clarification_question"),
        )

    except Exception as error:
        logger.warning(
            "LLM intent detection failed: %s. Falling back to rule-based.",
            error,
        )
        return detect_intent_rules(message)


def detect_intent_rules(message: str) -> IntentResult:
    detected_doc_type = _detect_document_type(message)
    client_name = _extract_client_name(message)

    if _is_greeting(message):
        return IntentResult(
            intent=IntentType.GREETING,
            confidence=0.95,
        )

    if _contains_keyword(message, UPLOAD_KEYWORDS):
        needs_clarification = not client_name or not detected_doc_type

        return IntentResult(
            intent=IntentType.UPLOAD_DOCUMENT,
            document_type=detected_doc_type,
            client_name=client_name,
            confidence=0.88 if not needs_clarification else 0.75,
            needs_clarification=needs_clarification,
            clarification_question=(
                "Sure — please tell me the client name and document type so I can upload it correctly."
                if needs_clarification
                else None
            ),
        )

    if _contains_keyword(message, STORE_KEYWORDS):
        needs_clarification = not client_name or not detected_doc_type

        return IntentResult(
            intent=IntentType.STORE_DOCUMENT,
            document_type=detected_doc_type,
            client_name=client_name,
            confidence=0.86 if not needs_clarification else 0.72,
            needs_clarification=needs_clarification,
            clarification_question=(
                "Sure — which client is this for, and what document type is it?"
                if needs_clarification
                else None
            ),
        )

    if _contains_keyword(message, SEARCH_KEYWORDS):
        needs_clarification = not client_name and not detected_doc_type

        return IntentResult(
            intent=IntentType.SEARCH_DOCUMENTS,
            document_type=detected_doc_type,
            client_name=client_name,
            confidence=0.85,
            needs_clarification=needs_clarification,
            clarification_question=(
                "What would you like me to search for — a client name, project, or document type?"
                if needs_clarification
                else None
            ),
        )

    if _contains_keyword(message, LIST_TEMPLATE_KEYWORDS):
        return IntentResult(
            intent=IntentType.LIST_TEMPLATES,
            confidence=0.9,
        )

    if _contains_keyword(message, LIST_CLIENTS_KEYWORDS):
        return IntentResult(
            intent=IntentType.LIST_CLIENTS,
            confidence=0.9,
        )

    if detected_doc_type:
        explicit_fetch = _contains_keyword(message, FETCH_KEYWORDS)

        return IntentResult(
            intent=IntentType.FETCH_TEMPLATE,
            document_type=detected_doc_type,
            client_name=client_name,
            confidence=0.92 if explicit_fetch else 0.78,
            needs_clarification=False,
            clarification_question=None,
        )

    if _contains_keyword(message, FETCH_KEYWORDS):
        return IntentResult(
            intent=IntentType.FETCH_TEMPLATE,
            confidence=0.68,
            needs_clarification=True,
            clarification_question=(
                "I can fetch a template for you — which one do you need? "
                "Available templates: FRD, Data Management Plan, HLD, LLD, Software Requirements."
            ),
        )

    return IntentResult(
        intent=IntentType.CLARIFY_INTENT,
        confidence=0.3,
        needs_clarification=True,
        clarification_question=(
            "I’m not fully sure what you need. I can help you fetch a template, upload/store a document, "
            "list templates, list clients, or search documents. What would you like to do?"
        ),
    )


async def detect_intent(
    message: str,
    history: list,
) -> IntentResult:
    api_key = os.getenv("OPENAI_API_KEY")

    if api_key:
        client = AsyncOpenAI(api_key=api_key)
        return await detect_intent_llm(message, history, client)

    logger.info("No OPENAI_API_KEY found — using rule-based intent detection")
    return detect_intent_rules(message)

