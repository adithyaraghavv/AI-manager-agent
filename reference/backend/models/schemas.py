from enum import Enum
from typing import Optional, List, Any
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    FETCH_TEMPLATE = "FETCH_TEMPLATE"
    UPLOAD_DOCUMENT = "UPLOAD_DOCUMENT"
    STORE_DOCUMENT = "STORE_DOCUMENT"
    LIST_TEMPLATES = "LIST_TEMPLATES"
    LIST_CLIENTS = "LIST_CLIENTS"
    FETCH_CLIENT_DOCUMENTS = "FETCH_CLIENT_DOCUMENTS"
    FETCH_CLIENT_DOCUMENT = "FETCH_CLIENT_DOCUMENT"
    SEARCH_DOCUMENTS = "SEARCH_DOCUMENTS"
    GREETING = "GREETING"
    CLARIFY_INTENT = "CLARIFY_INTENT"
    UNKNOWN = "UNKNOWN"


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    conversation_history: List[ChatMessage] = Field(default_factory=list)
    session_id: Optional[str] = None


class TemplateInfo(BaseModel):
    name: str
    document_type: Optional[str] = None
    filename: str
    extension: str = ""
    download_url: str
    size_kb: Optional[float] = None


class DocumentInfo(BaseModel):
    filename: str
    display_name: str = ""
    client_name: str
    document_type: Optional[str] = None
    extension: str = ""
    file_path: str
    uploaded_at: Optional[str] = None
    size_kb: Optional[float] = None
    download_url: str = ""


class ClientInfo(BaseModel):
    client_name: str
    folder_name: str
    document_count: int = 0
    documents: List[DocumentInfo] = Field(default_factory=list)


class IntentResult(BaseModel):
    intent: IntentType
    document_type: Optional[str] = None
    client_name: Optional[str] = None
    document_query: Optional[str] = None
    matched_filename: Optional[str] = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    template_name: Optional[str] = None


class ChatResponse(BaseModel):
    message: str
    intent: IntentType
    document_type: Optional[str] = None
    client_name: Optional[str] = None
    action: Optional[str] = None
    download_url: Optional[str] = None
    available_templates: Optional[List[Any]] = None
    clients: Optional[List[Any]] = None
    session_id: str
    success: bool = True
