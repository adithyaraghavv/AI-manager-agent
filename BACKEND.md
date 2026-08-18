# DocuBot / MarBot — Backend Documentation

> **STALE — do not trust the module layout below.**
>
> This document describes the legacy `backend/{main.py, routers/, services/, models/}`
> tree, which has been deleted. The real FastAPI app lives at
> **`backend/app/main.py:app`** with services under `backend/app/services/` and
> routers under `backend/app/api/routes_*`. See
> [`backend/README.md`](backend/README.md) for the current layout. This file is
> kept only for historical context and will be rewritten separately.

This document explains **what the backend does** (functionality delivered so far) and **how the code is organised**, module by module.

---

## 1. What the Backend Does (Functionality Overview)

The backend powers **MarBot**, an AI‑assisted Project Management Document Assistant. Through a small set of REST endpoints it lets a Project Manager:

1. **Chat in natural language** and have their intent understood (e.g. *“fetch the HLD template”*, *“show docs for ABCD”*, *“upload the FRD for Alpha”*).
2. **Fetch document templates** — templates are auto‑discovered from a `Templates/` folder; users can list them, download them, or ask for one by name/abbreviation (`FRD`, `HLD`, `LLD`, `SRS`, `DMP`, or free text).
3. **Upload completed documents** into a per‑client folder tree that follows a standard 7‑phase SDLC layout.
4. **Browse client documents** — list all clients, drill into a client, or search across every stored document.
5. **Download stored files safely** — every path is validated to prevent traversal attacks.
6. **Generate natural, grounded replies** — using GPT‑4o‑mini when an API key is present, and a curated rule‑based fallback otherwise, so the app works offline.

### Key end‑user capabilities

| Capability | Trigger example | Backend behaviour |
|---|---|---|
| Greet / help menu | “hi”, “hello” | Returns a friendly menu of possible actions. |
| Fetch template | “Give me the FRD template” | Detects `FETCH_TEMPLATE`, matches best template, returns a `download_url`. |
| List templates | “list all templates” | Returns metadata for every file in `Templates/`. |
| List clients | “list clients”, “show projects” | Returns every client folder + document counts. |
| Client documents | “documents for ABCD” | Returns that client’s docs (2 levels deep). |
| Search | “find UAT” | Case‑insensitive substring search across all stored docs. |
| Upload document | Upload form → `POST /api/upload` | Auto‑routes into the correct phase subfolder, renames with timestamp. |
| Detect doc type | Upload widget calls `/upload/detect-type` | Suggests a document type from the filename. |

### Non‑functional properties already implemented

- **Zero‑config discovery** — drop a file into `Templates/` or `Clients/<Name>/`, it appears in the API.
- **LLM + rule‑based fallback** on both intent detection and reply generation.
- **Grounded prompts** — the LLM is given the *real* filenames on disk, so it cannot invent template names.
- **Path‑safety** — allowed extensions, size limits (50 MB), `startswith(PROJECT_ROOT)` checks, `os.path.basename()` sanitisation.
- **Backwards compatibility** — both the modern `Clients/<name>/` layout and the legacy flat `Clients_<...>/` layout are recognised.
- **Session id + short conversation history** so multi‑turn dialogs (e.g. clarification questions) work without any server‑side store.

---

## 2. Tech Stack

| Package               | Role                                                       |
|-----------------------|------------------------------------------------------------|
| `fastapi>=0.115`      | Web framework and OpenAPI docs.                            |
| `uvicorn[standard]`   | ASGI server used to run FastAPI.                           |
| `python-multipart`    | Required for `UploadFile` / `Form` parsing.                |
| `openai>=1.50`        | Async client for GPT‑4o‑mini.                              |
| `pydantic>=2.10`      | Data validation and typed models.                          |
| `python-dotenv`       | Load `OPENAI_API_KEY` from `.env`.                         |
| `aiofiles`            | Async file I/O helper.                                     |

Run locally (PowerShell):

```powershell
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Interactive docs: `http://localhost:8000/docs` — health check: `/health`.

---

## 3. Project Layout

```
backend/
├── main.py                    # FastAPI app, CORS, startup, router mounting
├── requirements.txt
├── models/
│   ├── __init__.py
│   └── schemas.py             # Pydantic models + IntentType enum
├── routers/
│   ├── __init__.py
│   ├── chat.py                # POST /api/chat  (orchestrator)
│   ├── templates.py           # GET  /api/templates/*
│   ├── upload.py              # POST /api/upload
│   └── documents.py           # GET  /api/documents/*
└── services/
    ├── __init__.py
    ├── intent_service.py      # LLM + rule‑based intent detection
    ├── storage_service.py     # File CRUD + folder management
    └── chat_service.py        # Reply generation (LLM + fallback)
```

Three logical layers:

| Layer      | Folder            | Responsibility                                                       |
|------------|-------------------|----------------------------------------------------------------------|
| API        | `backend/routers` | HTTP endpoints.                                                      |
| Services   | `backend/services`| Business logic: intent, storage, reply.                              |
| Models     | `backend/models`  | Pydantic schemas + `IntentType` enum shared across the app.          |

---

## 4. `backend/main.py` — Application Entry Point

```python
app = FastAPI(title="PM Document Assistant API", version="2.0.0")
```

Responsibilities:

1. **Creates the FastAPI app** — metadata drives `/docs` (Swagger) and `/redoc`.
2. **Enables CORS** for local dev frontends (`localhost:3000`, `5173`, `127.0.0.1:5500`).
3. **`@app.on_event("startup")`** — ensures `Templates/` and `Clients/` directories exist (idempotent `os.makedirs(..., exist_ok=True)`).
4. **Mounts four routers** under versioned prefixes and Swagger tags:
   - `/api/templates` → template listing/download
   - `/api/upload`    → file upload + doc‑type detection
   - `/api/chat`      → chatbot endpoint
   - `/api/documents` → browse/search/download stored client documents
5. **`GET /health`** — lightweight readiness probe.

---

## 5. `backend/models/schemas.py` — Data Contracts

Single source of truth for shapes exchanged between frontend, routers, and services.

### 5.1 `IntentType` (Enum)

- `FETCH_TEMPLATE` — user wants a blank template.
- `UPLOAD_DOCUMENT` / `STORE_DOCUMENT` — persist a completed doc.
- `LIST_TEMPLATES`, `LIST_CLIENTS`, `FETCH_CLIENT_DOCUMENTS`, `SEARCH_DOCUMENTS`.
- `GREETING`, `CLARIFY_INTENT`, `UNKNOWN` — conversational/edge cases.

Using an `Enum` catches typos early and keeps the API contract stable.

### 5.2 Request/Response models

| Model            | Purpose                                                                 |
|------------------|-------------------------------------------------------------------------|
| `ChatMessage`    | `{role, content}` — one conversation turn.                              |
| `ChatRequest`    | Body for `POST /api/chat`: message + prior `conversation_history` + optional `session_id`. |
| `ChatResponse`   | Returned to the UI: message, intent, action hint, `download_url`, lists, `session_id`, `success`. |
| `TemplateInfo`   | Metadata for a template file: name, filename, extension, `download_url`, size. |
| `DocumentInfo`   | Metadata for a stored client document (includes `file_path` and safe `download_url`). |
| `ClientInfo`     | Client name + folder + `document_count` + nested list of `DocumentInfo`. |
| `IntentResult`   | Output of the intent detector: `intent`, extracted entities, `confidence`, `needs_clarification`, `clarification_question`. |

`confidence` is constrained to `[0.0, 1.0]` via `Field(ge=0.0, le=1.0)`.

---

## 6. `backend/services/intent_service.py` — Intent Detection

Answers a single question: **“What does the user want?”** → returns an `IntentResult`.

### 6.1 Dual‑mode architecture

```python
async def detect_intent(message, history) -> IntentResult:
    if os.getenv("OPENAI_API_KEY"):
        return await detect_intent_llm(...)
    return detect_intent_rules(message)
```

- **LLM mode** (preferred) — calls `gpt-4o-mini` with `response_format={"type": "json_object"}` so the model must return strict JSON.
- **Rule‑based fallback** — pure Python regex + keyword scan; fully usable offline.

### 6.2 LLM mode

`_build_system_prompt(template_names)` embeds the **actual filenames** currently on disk so the model can only match against real templates (prevents hallucinations — see CRITICAL RULE #4).

The prompt also contains explicit CRITICAL RULES to fix known ambiguities:

- “fetch clients” must be `LIST_CLIENTS`, not `FETCH_TEMPLATE`.
- Abbreviations `FRD`, `HLD`, `LLD`, `SRS`, `DMP` always mean `FETCH_TEMPLATE`.
- `client_name` only applies to `FETCH_CLIENT_DOCUMENTS` and `UPLOAD_DOCUMENT`.

The last 6 turns of `history` are forwarded to preserve short‑term context. The raw JSON reply is parsed and coerced through `_safe_intent()` / `_safe_float()` so a malformed value never crashes the router — worst case yields `IntentType.UNKNOWN`. On any exception the code **automatically falls back** to `detect_intent_rules()`.

### 6.3 Rule‑based mode

Ordered checks (order matters, and comments explain why):

1. `GREETING` — whole‑word match on “hi/hello/…”.
2. `LIST_CLIENTS` — **before** `FETCH_TEMPLATE` so “fetch clients” isn’t misread.
3. `UPLOAD_DOCUMENT` / `STORE_DOCUMENT` — before `FETCH_CLIENT_DOCUMENTS` so “upload doc for XYZ” isn’t caught by the client‑doc regex.
4. `FETCH_CLIENT_DOCUMENTS` — via `_CLIENT_DOC_PATTERNS` (5 regexes extracting client name from “documents for XYZ”, etc.).
5. `SEARCH_DOCUMENTS`, `LIST_TEMPLATES`.
6. `FETCH_TEMPLATE` — triggered by fetch verbs + doc abbreviations, but **not** if the word `client` appears (disambiguation).
7. Default → `CLARIFY_INTENT` with a helpful multi‑choice question.

`_extract_client_name_from_message` runs the same regex family plus a `for/from <name>` fallback, filtered by `_CLIENT_STOPWORDS` (so “template”, “please” are never treated as client names).

---

## 7. `backend/services/storage_service.py` — File System Layer

Owns **all** filesystem interactions and enforces path‑safety.

### 7.1 Configuration constants

- `ALLOWED_EXTENSIONS = {.docx, .doc, .pdf, .xlsx, .pptx, .txt}` — enforced on both list and upload.
- `MAX_UPLOAD_SIZE_BYTES = 50 MB`.
- `PROJECT_ROOT`, `TEMPLATES_DIR`, `CLIENTS_DIR` — resolved **once** at import time relative to the module’s own file, so paths work regardless of the current working directory.

### 7.2 The 7‑phase client folder structure

Every client automatically gets an SDLC‑style layout:

```
Clients/<Client>/
  1. Pre-requisites
  2. Requirement Analysis
  3. System Design
  4. Implementation (Coding)
  5. Testing (STLC integrated)
  6. Deployment
  7. Maintenance
```

`_TYPE_TO_SUBFOLDER` is an **ordered** list of `(keywords → subfolder)`. Order matters: more specific phrases (`"test summary"`) come before generic ones (`"test case"`). `_detect_phase_folder()` normalises `document_type + filename`, walks the list, and returns the first hit — defaults to `"1. Pre-requisites"`.

`_create_client_subfolders()` guarantees all 7 phase folders exist whenever a client folder is touched.

### 7.3 Template discovery — `list_templates()`

Scans `Templates/` on every call and produces a `TemplateInfo` for each valid file:

- Human‑friendly `name` from `_display_name_from_filename()` — strips `(QMS-126)`‑style tags, replaces `_`/`-` with spaces.
- URL‑safe `download_url` using `urllib.parse.quote` (handles spaces).
- File size in KB.

Result: **zero‑config** for new templates — drop a file and it appears in the API.

### 7.4 Fuzzy template matching — `find_best_template()`

Combines three signals to score each template:

1. `difflib.SequenceMatcher` ratio between the normalised query and the template’s searchable text.
2. **Token‑overlap bonus** (`× 1.2`) — critical for abbreviations. Query tokens are enriched via `_QUERY_PHRASE_TO_ABBREV` (e.g. “high level design” → also add `hld`); template text is enriched via `_PHRASE_TO_ABBREV`, so an abbreviation can match a spelled‑out name.
3. Exact‑substring bonus (`+ 0.7`) and explicit `document_type` bonus (`+ 1.2`).

Returns the best hit only if score ≥ `minimum_score` (default `0.3`), else `None`.

### 7.5 Client discovery — `_discover_client_locations()`

Supports **two** on‑disk layouts:

- **Standard**: `Clients/<name>/…`
- **Legacy / flat**: `Clients_<something>/…` at project root.

Uses `os.path.realpath` in a `seen` set for symlink/duplicate de‑duplication. Returns `(client_name, folder_name, absolute_path)` triples.

`_collect_documents_in_folder()` walks up to **2 subdirectory levels**, skips folders it can’t read (`PermissionError`), produces `DocumentInfo` objects sorted by `uploaded_at` descending.

### 7.6 Security — `get_client_file_path()`

Anti‑path‑traversal check for `/api/documents/client-file`:

1. Normalises separators and resolves to an absolute path.
2. Rejects anything not starting with `PROJECT_ROOT + os.sep` (blocks `../../`).
3. Requires the path to live under `CLIENTS_DIR` **or** a legacy `Clients_*` folder.
4. Requires the file to exist with an allowed extension.
5. Logs traversal attempts (`logger.warning`).

Returns `None` on any failure → the router responds `404`, never leaking the reason.

### 7.7 Storing an upload — `store_document()`

Called by `POST /api/upload`:

1. Ensures the client folder + 7 phase subfolders exist.
2. Routes to the correct phase via `_detect_phase_folder(document_type, original_filename)`.
3. Builds a collision‑proof filename: `<client>_<type>_<YYYYMMDD_HHMMSS>.<ext>`, using `_sanitize_folder_name()`.
4. Uses `shutil.move()` (not `copy`) so the temp file from the router is cleaned up in the same call.
5. Returns a `DocumentInfo` with a safe relative `download_url`.

### 7.8 Miscellaneous helpers

- `search_documents(query)` — case‑insensitive substring search across filename, client name, document type.
- `list_client_documents(client_name=None)` — flat list for `/api/documents`.
- `detect_doc_type_from_content_or_filename()` — used by `/api/upload/detect-type` to pre‑fill the UI’s type field.

---

## 8. `backend/services/chat_service.py` — Reply Generation

Turns an `IntentResult` + an `action_outcome` string (produced by the chat router) into the natural‑language message shown to the user.

### 8.1 Dual‑mode again

- **With `OPENAI_API_KEY`** → `_llm_response()` calls `gpt-4o-mini` with:
  - A persona system prompt (`ASSISTANT_PERSONA` — “MarBot”, professional/friendly, markdown, one clarification question at a time, no invented names).
  - A `[Context: ...]` block containing intent + entities + outcome, so the model’s reply is **grounded** in what the router actually did.
  - The last 6 conversation turns, normalised via `_role_map` (UI’s `"bot"` → OpenAI’s `"assistant"`).
- **Without a key**, or if the LLM call fails → `_rule_based_response()` returns a curated markdown reply per intent (greeting menu, template confirmation, upload prompt, empty‑state messages).

The router never needs to know which path was used — it simply awaits `generate_response(...)`.

---

## 9. Routers — HTTP Surface

### 9.1 `routers/chat.py` — `POST /api/chat`

The orchestrator:

1. Generate a `session_id` if the client didn’t send one.
2. Reject empty messages with `400`.
3. `detect_intent(...)` → `IntentResult`.
4. **`match intent.intent:`** — Python 3.10 structural pattern matching selects behaviour:
   - `FETCH_TEMPLATE`: prefer the LLM‑selected `matched_filename` (validated via `get_template_path`), else fuzzy‑match with `find_best_template`. On success set `action="download"` + `download_url`. Otherwise return the full template list so the UI can render a picker.
   - `LIST_TEMPLATES`: return `list_templates()`.
   - `UPLOAD_DOCUMENT` / `STORE_DOCUMENT`: `action="upload_prompt"` — frontend opens the upload widget.
   - `LIST_CLIENTS`: return `list_all_clients()`.
   - `FETCH_CLIENT_DOCUMENTS`: `find_client_documents(name)`; on miss gracefully degrade to the client list.
   - `SEARCH_DOCUMENTS`: forward the raw message to `search_documents(...)`.
   - `GREETING` / `CLARIFY_INTENT` / default: no side effects, just build a message.
5. Compose `bot_message` via `generate_response(...)` using intent + `action_outcome`.
6. Return a fully populated `ChatResponse`.

Each branch also builds a short `action_outcome` string (“Found 3 clients”, “needs clarification”, …) so the LLM reply is grounded in what really happened.

### 9.2 `routers/templates.py`

- `GET /api/templates/` → list all templates.
- `GET /api/templates/{doc_type}` → metadata for the best fuzzy match; on miss returns `404` with the full list of alternatives in the error body.
- `GET /api/templates/download/{filename}` → streams the file via `FileResponse` with the correct MIME type. `os.path.basename(filename)` protects against traversal.

### 9.3 `routers/upload.py` — `POST /api/upload`

Multipart handler:

1. Requires `client_name` (or `project_name`) and `document_type`.
2. Reads bytes and validates:
   - Filename present.
   - Extension in `ALLOWED_EXTENSIONS`.
   - Non‑empty, ≤ `MAX_UPLOAD_SIZE_MB` (returns `413` if too big).
3. Writes to a temp file (`tempfile.gettempdir()`), then `store_document(...)` `shutil.move`s it into the correct phase folder.
4. On any exception cleans up the temp file, logs the traceback (`logger.exception`), and returns `500`.
5. Also exposes `POST /api/upload/detect-type` to help the frontend pre‑fill the type field.

### 9.4 `routers/documents.py`

- `GET /api/documents/` → all documents; optional `?client=` filter.
- `GET /api/documents/clients` → client list with a friendly empty‑state message.
- `GET /api/documents/search?q=` → substring search.
- `GET /api/documents/client-file?path=` → **safe download** via `get_client_file_path()`; MIME type guessed with `mimetypes`.
- `GET /api/documents/download?file_path=` → **legacy** absolute‑path download; still validates the path is inside `PROJECT_ROOT` and exists.

---

## 10. End‑to‑End Request Traces

### 10.1 “Give me the HLD template”

1. `POST /api/chat` with `{message: "Give me the HLD template"}`.
2. `detect_intent()` → LLM returns `{intent: FETCH_TEMPLATE, matched_filename: "Marlabs (QMS-144) High Level Design- DE - Template.docx"}`.
3. `chat.py` validates the filename via `get_template_path()`, finds the matching `TemplateInfo`, sets `action="download"`, `download_url="/api/templates/download/..."`.
4. `chat_service.generate_response()` composes “Here’s your **HLD** template! Click download below…”.
5. Frontend renders a download button → `GET /api/templates/download/<file>` streams the `.docx`.

### 10.2 “Upload the FRD for ABCD”

1. Frontend opens the upload modal (triggered by an earlier `action="upload_prompt"`).
2. `POST /api/upload` with the file, `client_name="ABCD"`, `document_type="FRD"`.
3. `upload.py` validates extension/size, writes to temp.
4. `store_document()` calls `_detect_phase_folder("FRD", filename)` → `"2. Requirement Analysis"`, ensures `Clients/ABCD/2. Requirement Analysis/` exists, renames to `abcd_frd_20260713_101500.docx`, moves it in.
5. Response includes the new `DocumentInfo` with a safe `download_url`.

### 10.3 “Show me all documents for ABCD”

1. `POST /api/chat` → intent `FETCH_CLIENT_DOCUMENTS`, `client_name="ABCD"`.
2. `find_client_documents("ABCD")` scans both standard and legacy layouts, collects docs (2 levels deep) from `Clients/ABCD/`.
3. Response contains `clients: [ClientInfo(...)]`; the UI renders a list with per‑document download buttons pointing at `/api/documents/client-file?path=...`.

---

## 11. Design Choices Worth Highlighting

- **Zero‑config templates & clients** — everything is discovered from the filesystem on demand; admins just drop/rename files.
- **LLM with rule‑based fallback** on both intent and reply generation — graceful degradation without an API key.
- **Grounded LLM prompts** — the intent prompt embeds real filenames; the reply prompt embeds the actual action outcome — dramatically reduces hallucination.
- **Enum‑driven control flow** — `IntentType` + `match/case` in the router keep orchestration readable and exhaustively checkable.
- **Path‑safety everywhere** — `os.path.basename()`, `startswith(PROJECT_ROOT)`, allowed extensions, and a dedicated `get_client_file_path()`.
- **Phase‑based storage** — uploads are auto‑routed to the correct SDLC phase folder from keywords in `document_type` + filename.
- **Backwards compatibility** — both new `Clients/<name>/` and legacy `Clients_<...>/` layouts are recognised.
- **Session id + short conversation history** — enables multi‑turn dialogs without any server‑side state store.
