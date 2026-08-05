# DocuBot — PM Document Assistant
## Complete System Design & Implementation Guide

---

## 1. System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        React Frontend                            │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ ChatWindow  │  │ FileUploader │  │  Template Grid/Cards   │  │
│  │ (messages,  │  │ (drag-drop,  │  │  (browse, download)    │  │
│  │  bubbles,   │  │  form modal) │  │                        │  │
│  │  input)     │  │              │  │                        │  │
│  └──────┬──────┘  └──────┬───────┘  └──────────┬─────────────┘  │
│         └────────────────┴──────────────────────┘                │
│                          │  HTTP/REST                            │
└──────────────────────────┼───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                      FastAPI Backend                             │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ /api/chat   │  │/api/templates│  │   /api/upload          │  │
│  │             │  │              │  │   /api/documents        │  │
│  └──────┬──────┘  └──────┬───────┘  └──────────┬─────────────┘  │
│         │                │                      │                │
│  ┌──────▼────────────────▼──────────────────────▼─────────────┐  │
│  │               Services Layer                               │  │
│  │  intent_service.py │ storage_service.py │ chat_service.py  │  │
│  └──────┬──────────────────────────────────────────────────────┘  │
│         │                                                        │
│  ┌──────▼──────┐  ┌─────────────────────────────────────────┐   │
│  │ OpenAI API  │  │         Local File System               │   │
│  │ (GPT-4o)   │  │  Templates/  │  Clients/{Name}/{Type}/  │   │
│  └─────────────┘  └─────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## 2. Data Flow: Complete Request Lifecycle

### A. Template Fetch Flow
```
User: "fetch me the SOW template"
  │
  ▼
React → POST /api/chat { message, history }
  │
  ▼
intent_service.detect_intent()
  ├─ OpenAI: intent=FETCH_TEMPLATE, doc_type=SOW
  └─ (fallback) rule-based keyword match
  │
  ▼
storage_service.get_template_path(SOW)
  └─ Scans Templates/ for *sow*.docx → returns path
  │
  ▼
chat_service.generate_response()
  └─ Returns: "✅ Here's the SOW template…"
  │
  ▼
ChatResponse {
  message: "Here's the SOW…",
  action: "download",
  download_url: "/api/templates/download/sow_template.docx"
}
  │
  ▼
React renders download button → user clicks → GET /api/templates/download/sow_template.docx
  └─ FileResponse streams the .docx
```

### B. Document Upload Flow
```
User drags file into Upload Modal
  │
  ▼
React: POST /api/upload (multipart/form-data)
  { file, client_name="Acme", document_type="SOW" }
  │
  ▼
upload.router validates:
  ├─ Extension in allowed set
  ├─ DocumentType is valid enum
  └─ client_name not empty
  │
  ▼
storage_service.store_document()
  ├─ get_client_folder("Acme", SOW) → Clients/Acme/SOW/
  ├─ Timestamps filename: acme_sow_20240115_143022.docx
  └─ shutil.move(tmp_path, dest_path)
  │
  ▼
Return { success: true, document: { filename, client_name, file_path } }
  │
  ▼
React: show success toast + bot confirmation message
```

---

## 3. Project File Structure

```
pm-chatbot/
├── backend/
│   ├── main.py                    # FastAPI app, CORS, startup
│   ├── requirements.txt
│   ├── .env                       # OPENAI_API_KEY=sk-...
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py             # Pydantic models, Enums
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── chat.py                # POST /api/chat
│   │   ├── templates.py           # GET /api/templates/*
│   │   ├── upload.py              # POST /api/upload
│   │   └── documents.py           # GET /api/documents/*
│   └── services/
│       ├── __init__.py
│       ├── intent_service.py      # LLM + rule-based intent detection
│       ├── storage_service.py     # File CRUD + folder management
│       └── chat_service.py        # Response generation
│
├── frontend/
│   └── index.html                 # Single-file React app (no build needed)
│
├── Templates/                     # Put your .docx templates here
│   ├── sow_template.docx
│   ├── frd_template.docx
│   ├── hld_template.docx
│   ├── lld_template.docx
│   ├── brd_template.docx
│   └── msa_template.docx
│
└── Clients/                       # Auto-created on upload
    ├── Acme_Corp/
    │   ├── SOW/
    │   │   └── acme_corp_sow_20240115_143022.docx
    │   └── FRD/
    └── XYZ_Ltd/
        └── HLD/
```

---

## 4. Step-by-Step Setup

### Step 1: Environment Setup

```bash
# Clone / create project directory
mkdir pm-chatbot && cd pm-chatbot

# Backend setup
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create .env file
echo "OPENAI_API_KEY=sk-your-key-here" > .env
```

### Step 2: Add Real Templates

```bash
# Place actual .docx files in the Templates folder
# Naming convention: {type}_template.docx (lowercase)
cp /path/to/your/sow.docx ../Templates/sow_template.docx
cp /path/to/your/frd.docx ../Templates/frd_template.docx
# etc.
```

### Step 3: Run the Backend

```bash
cd backend
uvicorn main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

Verify at: http://localhost:8000/health

### Step 4: Open the Frontend

```bash
# Option A: Open directly in browser
open frontend/index.html

# Option B: Simple HTTP server (avoids CORS on some browsers)
cd frontend
python -m http.server 3000
# Open: http://localhost:3000
```

### Step 5: Test the Full Workflow

1. **Fetch a template**: Type "fetch SOW template" → bot replies with download button
2. **Upload a document**: Click 📤 → fill in client name + type → drag/drop file
3. **Verify storage**: Check `Clients/` folder for organized files
4. **Search**: Type "find Acme documents" → bot lists stored files
5. **List templates**: Type "show all templates" → grid of available templates appears

---

## 5. API Reference

### POST /api/chat
```json
// Request
{
  "message": "fetch me the SOW template",
  "conversation_history": [
    {"role": "user", "content": "hello"},
    {"role": "assistant", "content": "Hi! How can I help?"}
  ],
  "session_id": "optional-uuid"
}

// Response
{
  "message": "✅ Here's the SOW template! Click download below.",
  "intent": "FETCH_TEMPLATE",
  "document_type": "SOW",
  "client_name": null,
  "action": "download",
  "download_url": "/api/templates/download/sow_template.docx",
  "available_templates": null,
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### GET /api/templates/
```json
{
  "templates": [
    {
      "name": "Sow Template",
      "document_type": "SOW",
      "filename": "sow_template.docx",
      "download_url": "/api/templates/download/sow_template.docx",
      "size_kb": 45.2
    }
  ],
  "count": 6
}
```

### POST /api/upload (multipart/form-data)
```
file:           [binary file data]
client_name:    "Acme Corporation"
document_type:  "SOW"
notes:          "Final version approved"
```
```json
// Response
{
  "success": true,
  "message": "Document stored successfully for client 'Acme Corporation'",
  "document": {
    "filename": "acme_corporation_sow_20240115_143022.docx",
    "client_name": "Acme Corporation",
    "document_type": "SOW",
    "file_path": "/path/to/Clients/Acme_Corporation/SOW/acme_corporation_sow_20240115_143022.docx",
    "uploaded_at": "2024-01-15T14:30:22",
    "size_kb": 128.4
  }
}
```

### GET /api/documents/?client=Acme
```json
{
  "documents": [
    {
      "filename": "acme_sow_20240115.docx",
      "client_name": "Acme",
      "document_type": "SOW",
      "file_path": "...",
      "uploaded_at": "2024-01-15T14:30:22",
      "size_kb": 128.4
    }
  ],
  "count": 1
}
```

---

## 6. Intent Detection Logic

```
User Message
    │
    ▼
┌─────────────────────────────────────┐
│  OPENAI_API_KEY in environment?     │
└─────────────────┬───────────────────┘
         YES ─────┤───── NO
                  │         │
                  ▼         ▼
          GPT-4o-mini   Rule-based
          JSON prompt   keyword match
                  │         │
                  └────┬────┘
                       ▼
               IntentResult {
                 intent: FETCH_TEMPLATE,
                 document_type: SOW,
                 client_name: "Acme",
                 confidence: 0.95,
                 needs_clarification: false
               }
```

### Supported Intents

| Intent | Example Triggers | Action |
|--------|-----------------|--------|
| `FETCH_TEMPLATE` | "fetch SOW", "get me the FRD template" | Return download URL |
| `UPLOAD_DOCUMENT` | "upload", "here's my document", "submit" | Show upload modal |
| `LIST_TEMPLATES` | "show all templates", "what templates do you have" | Return template grid |
| `SEARCH_DOCUMENTS` | "find Acme files", "search for HLD" | Return matching docs |
| `LIST_CLIENTS` | "show my clients", "list projects" | Return client list |
| `GREETING` | "hello", "hi", "hey" | Welcome message |
| `CLARIFY_INTENT` | Ambiguous input | Ask clarifying question |

---

## 7. Storage System Design

### Folder Naming Rules
- Client names are sanitized (special chars → `_`)
- File names include timestamp to prevent overwrites
- Format: `{client}_{type}_{YYYYMMDD_HHMMSS}{ext}`

### Extending to Cloud Storage (AWS S3)
Replace `storage_service.py` functions:

```python
import boto3

s3 = boto3.client("s3", region_name="us-east-1")
BUCKET = "pm-documents"

def store_document_s3(file_bytes, client_name, doc_type, filename):
    key = f"Clients/{client_name}/{doc_type}/{filename}"
    s3.put_object(Bucket=BUCKET, Key=key, Body=file_bytes)
    url = s3.generate_presigned_url("get_object",
        Params={"Bucket": BUCKET, "Key": key}, ExpiresIn=3600)
    return url
```

---

## 8. Chatbot Conversation Examples

```
# Example 1: Simple template fetch
User:  "I need the SOW template"
Bot:   "✅ Here's the SOW template! Click the download button below..."
       [Download SOW button]

# Example 2: Ambiguous query — clarification
User:  "I need a template"
Bot:   "I'd be happy to fetch a template! Which type do you need?
        Available: SOW, FRD, HLD, LLD, BRD, MSA"
User:  "FRD please"
Bot:   "✅ Here's the FRD template! Click the download button below..."
       [Download FRD button]

# Example 3: Upload with missing info
User:  "I want to upload my document"
Bot:   "📤 Great! Please use the upload button below to attach your
        completed document. I'll help you organize it."
       [Open Upload Dialog button]
→ User clicks, fills form, drops file → stored to Clients/{name}/{type}/

# Example 4: Multi-step workflow
User:  "fetch FRD for Acme Corp project"
Bot:   [Download FRD button]
User:  [Downloads, edits externally, comes back]
User:  "upload completed document"
Bot:   [Upload modal opens, client pre-filled if detected]
→ File stored to Clients/Acme_Corp/FRD/acme_corp_frd_20240115.docx
```

---

## 9. Environment Variables

```bash
# backend/.env
OPENAI_API_KEY=sk-...          # Optional: enables GPT-4o intent detection
                               # Without this, rule-based fallback is used

# Optional for production
PORT=8000
TEMPLATES_DIR=/absolute/path/to/Templates
CLIENTS_DIR=/absolute/path/to/Clients
```

---

## 10. Bonus Features (Implementation Notes)

### Auto-detect document type from filename
Already implemented in `storage_service.detect_doc_type_from_content_or_filename()`.
Called via `POST /api/upload/detect-type` before the user fills the form.

### Drag-and-drop upload
Implemented in the Upload Modal using native browser `dragover`/`drop` events.

### Document preview
To add `.docx` preview, use `mammoth` (npm) or `python-docx2txt`:
```python
# pip install docx2txt
import docx2txt
text = docx2txt.process("path/to/file.docx")
```
Then return `text` in the upload response for React to display.

### Extract client name from filename
Pattern: `{ClientName}_SOW_v2.docx` → parse before the document type keyword.
See `_detect_doc_type_from_filename()` in `storage_service.py` for extension point.
