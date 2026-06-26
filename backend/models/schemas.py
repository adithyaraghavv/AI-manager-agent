from enum import Enum
from typing import Optional, List, Any
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    FETCH_TEMPLATE = "FETCH_TEMPLATE"
    UPLOAD_DOCUMENT = "UPLOAD_DOCUMENT"
    STORE_DOCUMENT = "STORE_DOCUMENT"
    LIST_TEMPLATES = "LIST_TEMPLATES"
    LIST_CLIENTS = "LIST_CLIENTS"
    SEARCH_DOCUMENTS = "SEARCH_DOCUMENTS"
    GREETING = "GREETING"
    CLARIFY_INTENT = "CLARIFY_INTENT"
    UNKNOWN = "UNKNOWN"


class DocumentType(str, Enum):
    FRD = "FRD"
    DATA_MANAGEMENT_PLAN = "DATA_MANAGEMENT_PLAN"
    HLD = "HLD"
    LLD = "LLD"
    SOFTWARE_REQUIREMENTS = "SOFTWARE_REQUIREMENTS"
    OTHER = "OTHER"


DOCUMENT_TYPE_INPUT_MAP = {
    "FRD": DocumentType.FRD,
    "FUNCTIONAL REQUIREMENT": DocumentType.FRD,
    "FUNCTIONAL REQUIREMENTS": DocumentType.FRD,
    "FUNCTIONAL REQUIREMENTS DOCUMENT": DocumentType.FRD,
    "FUNCTIONAL SPECIFICATION": DocumentType.FRD,
    "FUNCTIONAL SPEC": DocumentType.FRD,

    "DATA_MANAGEMENT_PLAN": DocumentType.DATA_MANAGEMENT_PLAN,
    "DATA MANAGEMENT PLAN": DocumentType.DATA_MANAGEMENT_PLAN,
    "DATA MANAGEMENT": DocumentType.DATA_MANAGEMENT_PLAN,
    "DMP": DocumentType.DATA_MANAGEMENT_PLAN,
    "DATA PLAN": DocumentType.DATA_MANAGEMENT_PLAN,

    "HLD": DocumentType.HLD,
    "HIGH LEVEL DESIGN": DocumentType.HLD,
    "HIGH-LEVEL DESIGN": DocumentType.HLD,
    "ARCHITECTURE DOCUMENT": DocumentType.HLD,
    "ARCHITECTURE DOC": DocumentType.HLD,
    "SOLUTION DESIGN": DocumentType.HLD,

    "LLD": DocumentType.LLD,
    "LOW LEVEL DESIGN": DocumentType.LLD,
    "LOW-LEVEL DESIGN": DocumentType.LLD,
    "DETAILED DESIGN": DocumentType.LLD,
    "TECHNICAL DESIGN": DocumentType.LLD,

    "SOFTWARE_REQUIREMENTS": DocumentType.SOFTWARE_REQUIREMENTS,
    "SOFTWARE REQUIREMENTS": DocumentType.SOFTWARE_REQUIREMENTS,
    "SOFTWARE REQUIREMENTS TEMPLATE": DocumentType.SOFTWARE_REQUIREMENTS,
    "SOFTWARE REQUIREMENT": DocumentType.SOFTWARE_REQUIREMENTS,
    "REQUIREMENTS DOCUMENT": DocumentType.SOFTWARE_REQUIREMENTS,
    "REQUIREMENTS DOC": DocumentType.SOFTWARE_REQUIREMENTS,
    "SPECIFICATION DOCUMENT": DocumentType.SOFTWARE_REQUIREMENTS,
    "SRS": DocumentType.SOFTWARE_REQUIREMENTS,

    "OTHER": DocumentType.OTHER,
}


def normalize_document_type(value: Optional[str]) -> Optional[DocumentType]:
    if value is None:
        return None

    cleaned = str(value).strip().upper()
    if cleaned in {"", "NONE", "NULL"}:
        return None

    cleaned = cleaned.replace("-", " ").replace("/", " ")
    cleaned = " ".join(cleaned.split())

    if cleaned in DOCUMENT_TYPE_INPUT_MAP:
        return DOCUMENT_TYPE_INPUT_MAP[cleaned]

    try:
        return DocumentType(cleaned)
    except Exception:
        return None


def document_type_to_display(value: Optional[DocumentType | str]) -> Optional[DocumentType]:
    if value is None:
        return None

    if isinstance(value, str):
        enum_value = normalize_document_type(value)
    else:
        enum_value = value

    if enum_value is None:
        return None

    display_map = {
        DocumentType.FRD: "FRD",
        DocumentType.DATA_MANAGEMENT_PLAN: "Data Management Plan",
        DocumentType.HLD: "HLD",
        DocumentType.LLD: "LLD",
        DocumentType.SOFTWARE_REQUIREMENTS: "Software Requirements",
        DocumentType.OTHER: "OTHER",
    }
    return display_map.get(enum_value, enum_value.value)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    conversation_history: List[ChatMessage] = Field(default_factory=list)
    session_id: Optional[str] = None


class TemplateInfo(BaseModel):
    name: str
    document_type: str
    filename: str
    download_url: str
    size_kb: Optional[float] = None


class DocumentInfo(BaseModel):
    filename: str
    client_name: str
    document_type: str
    file_path: str
    uploaded_at: Optional[str] = None
    size_kb: Optional[float] = None


class IntentResult(BaseModel):
    intent: IntentType
    document_type: Optional[DocumentType] = None
    client_name: Optional[str] = None
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    template_name: Optional[str] = None


class ChatResponse(BaseModel):
    message: str
    intent: IntentType
    document_type: Optional[DocumentType] = None
    client_name: Optional[str] = None
    action: Optional[str] = None
    download_url: Optional[str] = None
    available_templates: Optional[List[Any]] = None
    session_id: str