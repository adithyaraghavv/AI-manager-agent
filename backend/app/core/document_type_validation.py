"""Checks whether an uploaded file actually looks like the document type the
PM selected for it, BEFORE it gets filed under that type.

This is a gate against misclassification (e.g. picking "Approved LLD" from
the dropdown but dragging in a SOW), not a bonus feature like RAG embedding
— so unlike embed_document, this fails CLOSED. Anything that stops us from
confidently confirming a match (no extractable text, the classification
call itself erroring out) reports UNCERTAIN or FAILED rather than waving
the upload through.
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum

from openai import OpenAI

from app.config import settings
from app.core.text_extraction import extract_text

logger = logging.getLogger(__name__)

CLASSIFICATION_MODEL = "gpt-4o-mini"
# Enough to give the classifier real signal without ballooning token cost —
# a document's type is almost always obvious from its opening section
# (title, headers, intro paragraph).
CONTENT_EXCERPT_CHARS = 3000

_SYSTEM_PROMPT = """You check whether an uploaded file actually is the document type a \
user claims it is, for a project-delivery document management system. \
You'll be given the file's original filename, the document type it was filed under, and \
(when available) an excerpt of its extracted text content.

Respond with ONLY a JSON object: {"outcome": "match" | "mismatch" | "uncertain", "reason": "<one short sentence>"}

- "match": the filename and/or content clearly indicate this IS the claimed document type.
- "mismatch": the filename and/or content clearly indicate this is a DIFFERENT, identifiable \
document type (e.g. claimed "Approved LLD" but the content is obviously a Statement of Work).
- "uncertain": there isn't enough signal to confidently say either way — a generic filename \
with no content excerpt, content that doesn't clearly read as any particular document type, \
or content that's ambiguous between the claimed type and something else. When genuinely unsure, \
prefer "uncertain" over guessing "match" — a wrongly-approved mismatch is worse than asking the \
user to double check.

Never invent details about the file that aren't in what you were given."""


class ValidationOutcome(Enum):
    MATCH = "match"
    MISMATCH = "mismatch"
    UNCERTAIN = "uncertain"
    FAILED = "failed"


@dataclass(frozen=True)
class DocumentTypeValidation:
    outcome: ValidationOutcome
    reason: str


def validate_document_type(
    content: bytes, extension: str, original_filename: str, doc_type: str
) -> DocumentTypeValidation:
    text = extract_text(content, extension)
    excerpt = text[:CONTENT_EXCERPT_CHARS] if text else None

    user_prompt = (
        f'Claimed document type: "{doc_type}"\n'
        f'Original filename: "{original_filename}"\n'
        + (
            f"Content excerpt:\n{excerpt}"
            if excerpt
            else "Content excerpt: (none available — this file format's text "
            "couldn't be extracted, judge from the filename alone)"
        )
    )

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=CLASSIFICATION_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        data = json.loads(response.choices[0].message.content)
        outcome = ValidationOutcome(data["outcome"])
        reason = str(data.get("reason", "")).strip()
        return DocumentTypeValidation(outcome=outcome, reason=reason)
    except Exception:
        logger.exception("Document type validation call failed for doc_type=%r", doc_type)
        return DocumentTypeValidation(
            outcome=ValidationOutcome.FAILED,
            reason="The validation check itself failed to run.",
        )
