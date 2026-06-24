"""
Data models for PM Document Assistant
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class DocumentType(str, Enum):
    SOW = "SOW"   # Statement of Work
    FRD = "FRD"   # Functional Requirements Document
    HLD = "HLD"   # High-Level Design
    LLD = "LLD"   # Low-Level Design
    BRD = "BRD"   # Business Requirements Document
    MSA = "MSA"   # Master Service Agreement
    OTHER = "OTHER"


class IntentType(str, Enum):
    FETCH_TEMPLATE   = "FETCH_TEMPLATE"
    UPLOAD_DOCUMENT  = "UPLOAD_DOCUMENT"
    STORE_DOCUMENT   = "STORE_DOCUMENT"
    LIST_TEMPLATES   = "LIST_TEMPLATES"
    LIST_CLIENTS     = "LIST_CLIENTS"
    SEARCH_DOCUMENTS = "SEARCH_DOCUMENTS"
    CLARIFY_INTENT   = "CLARIFY_INTENT"
    GREETING         = "GREETING"
    UNKNOWN          = "UNKNOWN"


# ─────────────────────────────────────────────
# Chat Models
# ─────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str
    timestamp: Optional[datetime] = None


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User's message")
    conversation_history: List[ChatMessage] = Field(
        default_factory=list,
        description="Previous messages for context"
    )
    session_id: Optional[str] = None


class IntentResult(BaseModel):
    intent: IntentType
    document_type: Optional[DocumentType] = None
    client_name: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None


class ChatResponse(BaseModel):
    message: str
    intent: Optional[IntentType] = None
    document_type: Optional[DocumentType] = None
    client_name: Optional[str] = None
    action: Optional[str] = None           # "download", "upload_prompt", etc.
    download_url: Optional[str] = None
    available_templates: Optional[List[str]] = None
    session_id: Optional[str] = None


# ─────────────────────────────────────────────
# Document / File Models
# ─────────────────────────────────────────────

class UploadRequest(BaseModel):
    client_name: str = Field(..., min_length=1)
    document_type: DocumentType
    notes: Optional[str] = None


class StoreRequest(BaseModel):
    filename: str
    client_name: str
    document_type: DocumentType


class DocumentInfo(BaseModel):
    filename: str
    client_name: str
    document_type: str
    file_path: str
    uploaded_at: Optional[str] = None
    size_kb: Optional[float] = None


class TemplateInfo(BaseModel):
    name: str
    document_type: str
    filename: str
    download_url: str
    size_kb: Optional[float] = None
