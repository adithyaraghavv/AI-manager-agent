"""
Intent Detection Service
Classifies user intent and extracts entities from messages.
Uses LLM when API key is available, rule-based fallback otherwise.
"""

import os
import re
import json
import logging
from typing import Optional, List

from openai import AsyncOpenAI

from models.schemas import IntentType, IntentResult

logger = logging.getLogger(__name__)


# ─── Keyword lists ────────────────────────────────────────────────────────────

_GREETING_KW = {"hello", "hi", "hey", "good morning", "good afternoon", "howdy"}

_LIST_CLIENTS_KW = [
    "list clients", "show clients", "fetch clients", "get clients",
    "list all clients", "show all clients", "active clients", "available clients",
    "existing clients", "what clients", "which clients", "clients do you",
    "list projects", "show projects", "fetch projects",
    "get projects", "all clients", "my clients",
]

_LIST_TEMPLATES_KW = [
    "list templates", "show templates", "available templates",
    "all templates", "what templates", "which templates", "template list",
    "list all templates", "show all templates",
]

_UPLOAD_KW = ["upload", "submit", "attach", "uploading", "here is my", "i am uploading"]
_STORE_KW = ["store", "save", "archive", "organize", "keep this"]
_SEARCH_KW = ["search", "find document", "find file", "locate document", "search document"]

_CLIENT_DOC_PATTERNS = [
    r"(?:fetch|get|show|download|list|find)\s+(?:completed\s+)?(?:documents?|docs?|files?)\s+(?:for|from|of|belonging\s+to)\s+([\w][\w\s&.\-]{0,60}?)(?:\s*$|\s+(?:please|thanks))",
    r"(?:get|download|fetch)\s+([\w][\w\s&.\-]{0,40}?)\s+(?:frd|hld|lld|srs|dmp|documents?|docs?|files?)",
    r"(?:documents?|files?|docs?)\s+(?:for|from|of)\s+([\w][\w\s&.\-]{0,60}?)(?:\s*$|\s+(?:please|thanks))",
    r"(?:fetch|show)\s+([\w][\w\s&.\-]{1,40}?)\s+(?:completed|uploaded)\s+(?:documents?|files?)",
    r"(?:files|documents|docs)\s+(?:in|under|inside)\s+([\w][\w\s&.\-]{1,60}?)(?:\s+folder)?(?:\s*$)",
]

_CLIENT_STOPWORDS = {
    "template", "templates", "the", "a", "an", "me", "my", "all",
    "please", "can", "could", "would", "some", "any",
}


# ─── Helper functions ─────────────────────────────────────────────────────────

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("-", " ").replace("/", " ")).strip()


def _has_kw(message: str, keywords: List[str]) -> bool:
    n = _norm(message)
    return any(_norm(kw) in n for kw in keywords)


def _is_greeting(message: str) -> bool:
    n = _norm(message)
    return any(re.search(rf"\b{re.escape(kw)}\b", n) for kw in _GREETING_KW)


def _extract_client_name_from_message(message: str) -> Optional[str]:
    """Try to extract a client name from a message using multiple patterns."""
    for pattern in _CLIENT_DOC_PATTERNS:
        m = re.search(pattern, message, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip(" .,-")
            if candidate.lower() not in _CLIENT_STOPWORDS and len(candidate) > 1:
                return candidate
    # Fallback: "for/from ClientName"
    m2 = re.search(
        r"(?:for|from)\s+([A-Za-z0-9][A-Za-z0-9&.\-\s]{1,60}?)(?:\s*$|\s+(?:template|document|file|please|thanks|doc)\b)",
        message, re.IGNORECASE
    )
    if m2:
        candidate = m2.group(1).strip()
        if candidate.lower() not in _CLIENT_STOPWORDS:
            return candidate
    return None


def _safe_intent(value: Optional[str]) -> IntentType:
    if not value:
        return IntentType.UNKNOWN
    try:
        return IntentType(str(value).strip().upper())
    except Exception:
        return IntentType.UNKNOWN


def _safe_float(value, default: float = 0.8) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return default


# ─── Rule-based detection ─────────────────────────────────────────────────────

def detect_intent_rules(message: str) -> IntentResult:
    msg = message.strip()

    if _is_greeting(msg):
        return IntentResult(intent=IntentType.GREETING, confidence=0.95)

    # LIST_CLIENTS must be checked before FETCH_TEMPLATE to avoid
    # "fetch clients" → FETCH_TEMPLATE mismatch
    if _has_kw(msg, _LIST_CLIENTS_KW):
        return IntentResult(intent=IntentType.LIST_CLIENTS, confidence=0.93)

    # UPLOAD / STORE checked before FETCH_CLIENT_DOCUMENTS so that
    # "upload document for XYZ" is not caught by the client-doc patterns
    if _has_kw(msg, _UPLOAD_KW):
        client = _extract_client_name_from_message(msg)
        needs_cl = not client
        return IntentResult(
            intent=IntentType.UPLOAD_DOCUMENT,
            client_name=client,
            confidence=0.88 if client else 0.72,
            needs_clarification=needs_cl,
            clarification_question=(
                "Sure — which client is this for, and what document type is it?"
                if needs_cl else None
            ),
        )

    if _has_kw(msg, _STORE_KW):
        client = _extract_client_name_from_message(msg)
        needs_cl = not client
        return IntentResult(
            intent=IntentType.STORE_DOCUMENT,
            client_name=client,
            confidence=0.86 if client else 0.70,
            needs_clarification=needs_cl,
            clarification_question=(
                "Which client folder should I store this under, and what document type?"
                if needs_cl else None
            ),
        )

    # FETCH_CLIENT_DOCUMENT: doc-type keyword + client name in same message
    # e.g. "give me the LLD doc for Hillenbrand", "fetch ABCD FRD",
    #      "download HLD of Alpha", "share Hillenbrand's LLD"
    _DOC_TYPE_TOKENS = {
        "frd": "FRD", "hld": "HLD", "lld": "LLD", "srs": "SRS",
        "dmp": "DMP", "brd": "BRD",
    }
    _DOC_TYPE_PHRASES = [
        ("high level design", "HLD"),
        ("low level design", "LLD"),
        ("functional requirement", "FRD"),
        ("business requirement", "BRD"),
        ("software requirement", "SRS"),
        ("data management", "DMP"),
        ("kickoff", "Kickoff"),
        ("kick off", "Kickoff"),
        ("test summary", "Test Summary"),
        ("test plan", "Test Plan"),
        ("test case", "Test Case"),
        ("release note", "Release Note"),
    ]

    msg_norm = _norm(msg)
    found_type: Optional[str] = None
    for phrase, label in _DOC_TYPE_PHRASES:
        if phrase in msg_norm:
            found_type = label
            break
    if not found_type:
        for tok, label in _DOC_TYPE_TOKENS.items():
            if re.search(rf"\b{tok}\b", msg_norm):
                found_type = label
                break

    if found_type:
        client = _extract_client_name_from_message(msg)
        # Also try patterns like "<Client> FRD", "<Client>'s LLD", "<Client> HLD doc"
        if not client:
            m = re.search(
                r"\b([A-Za-z][A-Za-z0-9&.\-]{1,40})(?:'s|s')?\s+"
                r"(?:frd|hld|lld|srs|dmp|brd|high level|low level|"
                r"functional|business|software|data management|kickoff|"
                r"kick off|test|release)\b",
                msg, re.IGNORECASE,
            )
            if m:
                candidate = m.group(1).strip()
                if (candidate.lower() not in _CLIENT_STOPWORDS
                        and candidate.lower() not in {"the", "a", "an", "my", "our",
                                                       "give", "get", "fetch",
                                                       "download", "show", "send",
                                                       "share", "provide"}):
                    client = candidate
        if client:
            return IntentResult(
                intent=IntentType.FETCH_CLIENT_DOCUMENT,
                client_name=client,
                document_type=found_type,
                confidence=0.9,
            )

    # FETCH_CLIENT_DOCUMENTS: "docs for XYZ", "get XYZ files", etc.
    for pattern in _CLIENT_DOC_PATTERNS:
        m = re.search(pattern, msg, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip(" .,-")
            first_word = candidate.lower().split()[0] if candidate.split() else ""
            if (candidate.lower() not in _CLIENT_STOPWORDS
                    and first_word not in _CLIENT_STOPWORDS
                    and len(candidate) > 1):
                return IntentResult(
                    intent=IntentType.FETCH_CLIENT_DOCUMENTS,
                    client_name=candidate,
                    confidence=0.87,
                )

    # SEARCH
    if _has_kw(msg, _SEARCH_KW):
        client = _extract_client_name_from_message(msg)
        return IntentResult(
            intent=IntentType.SEARCH_DOCUMENTS,
            client_name=client,
            confidence=0.85,
        )

    # LIST_TEMPLATES
    if _has_kw(msg, _LIST_TEMPLATES_KW):
        return IntentResult(intent=IntentType.LIST_TEMPLATES, confidence=0.92)

    # FETCH_TEMPLATE — only if "client" is NOT the focus
    _DOC_ABBREVS = {"frd", "hld", "lld", "srs", "dmp"}
    fetch_words = {
        "fetch", "get", "download", "give me", "send me", "provide",
        "template", "need a", "need the", "i need", "can i get", "want a",
        "want the", "looking for",
    } | _DOC_ABBREVS
    msg_lower = msg.lower()
    has_fetch = any(w in msg_lower for w in fetch_words)

    if has_fetch and "client" not in msg_lower:
        return IntentResult(
            intent=IntentType.FETCH_TEMPLATE,
            confidence=0.70,
            needs_clarification=True,
            clarification_question=(
                "I can fetch a template for you. Which template do you need? "
                "Available templates include FRD, HLD, LLD, Software Requirements, and Data Management Plan."
            ),
        )

    return IntentResult(
        intent=IntentType.CLARIFY_INTENT,
        confidence=0.3,
        needs_clarification=True,
        clarification_question=(
            "I'm not sure what you need. I can:\n"
            "• **Fetch a template** — e.g. 'Give me the FRD template'\n"
            "• **Upload a document** — e.g. 'Upload completed FRD for XYZ'\n"
            "• **List clients** — e.g. 'Show all clients'\n"
            "• **Get client documents** — e.g. 'Show documents for XYZ'\n"
            "What would you like to do?"
        ),
    )


# ─── LLM-based detection ──────────────────────────────────────────────────────

def _build_system_prompt(template_names: List[str]) -> str:
    if template_names:
        tpl_list = "\n".join(f"  - {n}" for n in template_names)
    else:
        tpl_list = "  (no templates currently available)"

    return f"""You are an intent classifier for a Project Management Document Assistant.

Available template files:
{tpl_list}

Classify the user message into exactly one intent:
- FETCH_TEMPLATE     : User wants to download/get a template to work from.
- UPLOAD_DOCUMENT    : User wants to upload or submit a completed document.
- STORE_DOCUMENT     : User wants to save/archive a document.
- LIST_TEMPLATES     : User wants to see all available templates.
- LIST_CLIENTS       : User wants to see all clients/projects. Triggered by: "list clients", "show clients", "fetch clients", "active clients", "list projects".
- FETCH_CLIENT_DOCUMENTS : User wants to see or download ALL completed docs for a specific client. Triggered by: "documents for XYZ", "files for XYZ", "get XYZ files".
- FETCH_CLIENT_DOCUMENT  : User wants ONE specific document type for a specific client. Triggered by phrases that combine a document type (FRD/HLD/LLD/SRS/DMP/BRD/etc.) AND a client name, e.g. "give me the LLD doc for Hillenbrand", "fetch ABCD FRD", "download HLD of Alpha", "share Hillenbrand's LLD". Set BOTH client_name and document_type.
- SEARCH_DOCUMENTS   : User wants to search stored documents.
- GREETING           : Hello, hi, good morning, etc.
- CLARIFY_INTENT     : Too vague to determine.
- UNKNOWN            : Unrelated to documents.

CRITICAL RULES:
1. "fetch clients", "list clients", "show clients", "get clients" → LIST_CLIENTS. NEVER FETCH_TEMPLATE.
2. "documents for <name>", "files for <name>", "get <name> docs" (WITHOUT a specific doc type) → FETCH_CLIENT_DOCUMENTS with client_name extracted.
3. If the message contains BOTH a doc-type keyword (FRD/HLD/LLD/SRS/DMP/BRD/kickoff/test/release) AND a client/project name → FETCH_CLIENT_DOCUMENT. Populate client_name AND document_type. Examples: "give me the LLD doc for Hillenbrand" → {{intent:"FETCH_CLIENT_DOCUMENT", client_name:"Hillenbrand", document_type:"LLD"}}; "fetch ABCD FRD" → {{client_name:"ABCD", document_type:"FRD"}}. NEVER classify these as FETCH_TEMPLATE.
4. FETCH_TEMPLATE (blank template): user wants a fresh template with NO client mentioned. Match matched_filename to ONE of the available template files listed above. If no file matches, set matched_filename to null and needs_clarification to true.
5. Do NOT invent template filenames. Only use filenames from the list above.
6. client_name is only relevant for FETCH_CLIENT_DOCUMENTS, FETCH_CLIENT_DOCUMENT, and UPLOAD_DOCUMENT.
7. Single abbreviations "FRD", "HLD", "LLD", "SRS", "DMP" alone or in short phrases with no client name ALWAYS mean FETCH_TEMPLATE. Match the corresponding file and set needs_clarification to false.

Respond ONLY with valid JSON:
{{
  "intent": "FETCH_TEMPLATE",
  "client_name": null,
  "document_type": null,
  "document_query": null,
  "matched_filename": "exact_filename.docx",
  "confidence": 0.95,
  "needs_clarification": false,
  "clarification_question": null
}}""".strip()


def _build_messages(message: str, history: list, template_names: List[str]) -> list:
    messages = [{"role": "system", "content": _build_system_prompt(template_names)}]
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
    template_names: List[str],
) -> IntentResult:
    messages = _build_messages(message, history, template_names)
    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
            max_tokens=350,
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        return IntentResult(
            intent=_safe_intent(data.get("intent")),
            document_type=data.get("document_type"),
            client_name=data.get("client_name"),
            document_query=data.get("document_query"),
            matched_filename=data.get("matched_filename"),
            confidence=_safe_float(data.get("confidence", 0.8)),
            needs_clarification=bool(data.get("needs_clarification", False)),
            clarification_question=data.get("clarification_question"),
        )
    except Exception as error:
        logger.warning("LLM intent detection failed: %s. Using rule-based fallback.", error)
        return detect_intent_rules(message)


async def detect_intent(message: str, history: list) -> IntentResult:
    """Main entry point: use LLM if available, else rule-based."""
    # Import here to avoid circular imports
    from services.storage_service import list_templates
    templates = list_templates()
    template_names = [t.filename for t in templates]

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        openai_client = AsyncOpenAI(api_key=api_key)
        return await detect_intent_llm(message, history, openai_client, template_names)

    logger.info("No OPENAI_API_KEY — using rule-based intent detection")
    return detect_intent_rules(message)
