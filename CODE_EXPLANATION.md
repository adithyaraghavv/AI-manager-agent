# DocuBot / PM Document Assistant — Detailed Code Explanation

> **STALE — do not trust the file paths below.**
>
> This document walks through the legacy `backend/{main.py, routers/, services/, models/}`
> tree, which has been deleted. The real FastAPI app lives at
> **`backend/app/main.py:app`** with services under `backend/app/services/` and
> routers under `backend/app/api/routes_*`. See
> [`backend/README.md`](backend/README.md) for the current layout. This file is
> kept only for historical context and will be rewritten separately.

This document is a deep, file‑by‑file walkthrough of the **backend** codebase in this workspace. It explains what every module does, how the pieces fit together, and how a request travels end‑to‑end (from a chat message to a downloaded template or a stored client document).

---

## 1. High‑Level Overview

DocuBot is an **AI‑assisted Project Management document assistant** built on:

- **FastAPI** — HTTP server, routing, dependency injection, auto‑generated OpenAPI docs.
- **Pydantic v2** — request/response validation via strongly‑typed models (`schemas.vpy`).
- **OpenAI (`gpt-4o-mini`)** — used for both **intent classification** and **natural‑language reply generation**, with a **rule‑based fallback** so the app works without an API key.
- **Local file system** — templates live in `Templates/`, uploaded client documents live in `Clients/<ClientName>/<PhaseFolder>/`.

The backend is organized in three layers:

| Layer      | Folder            | Responsibility                                                       |
|------------|-------------------|----------------------------------------------------------------------|
| API        | `backend/routers` | HTTP endpoints (chat, templates, upload, documents).                 |
| Services   | `backend/services`| Business logic: intent detection, storage, reply generation.         |
| Models     | `backend/models`  | Pydantic schemas + `IntentType` enum shared across the app.          |

Entry point: `backend/main.py`.

---

## 2. `backend/main.py` — Application Entry Point

```python
app = FastAPI(title="PM Document Assistant API", version="2.0.0")
```

Key responsibilities:

1. **Creates the FastAPI app** with metadata used by `/docs` (Swagger) and `/redoc`.
2. **Enables CORS** for the local dev frontends (`localhost:3000`, `5173`, `127.0.0.1:5500`) so the browser can call the API cross‑origin.
3. **`@app.on_event("startup")`** — before serving traffic, ensures the `Templates/` and `Clients/` directories exist (idempotent `os.makedirs(..., exist_ok=True)`).
4. **Mounts four routers** under versioned prefixes and Swagger tags:
   - `/api/templates` → template listing/download
   - `/api/upload`    → file upload + document type detection
   - `/api/chat`      → the chatbot endpoint
   - `/api/documents` → browse/search/download stored client documents
5. **`GET /health`** — lightweight readiness probe returning `{"status": "ok", ...}`.

---

## 3. `backend/models/schemas.py` — Data Contracts

All input/output is validated by Pydantic. This file is the single source of truth for the shapes exchanged between frontend, routers, and services.

### 3.1 `IntentType` (Enum)
The canonical set of intents the classifier can produce:

- `FETCH_TEMPLATE` — user wants a blank template to fill out.
- `UPLOAD_DOCUMENT` / `STORE_DOCUMENT` — user wants to persist a completed doc.
- `LIST_TEMPLATES`, `LIST_CLIENTS`, `FETCH_CLIENT_DOCUMENTS`, `SEARCH_DOCUMENTS`.
- `GREETING`, `CLARIFY_INTENT`, `UNKNOWN` — conversational/edge cases.

Using an `Enum` guarantees typos are caught early and the API contract is stable.

### 3.2 Request/Response models

| Model            | Purpose                                                                 |
|------------------|-------------------------------------------------------------------------|
| `ChatMessage`    | `{role, content}` — one turn in a conversation.                         |
| `ChatRequest`    | Body for `POST /api/chat`: message + prior `conversation_history` + optional `session_id`. |
| `ChatResponse`   | What the chat endpoint returns to the UI (message, intent, action hint, `download_url`, lists, `session_id`, `success`). |
| `TemplateInfo`   | Metadata for a template file: name, filename, extension, `download_url`, size. |
| `DocumentInfo`   | Metadata for a stored client document (includes `file_path` and safe `download_url`). |
| `ClientInfo`     | Client name + folder + `document_count` + nested list of `DocumentInfo`. |
| `IntentResult`   | Output of the intent detector: `intent`, extracted entities (`document_type`, `client_name`, `matched_filename`, ...), `confidence`, `needs_clarification`, `clarification_question`. |

`confidence` is constrained to `[0.0, 1.0]` via `Field(ge=0.0, le=1.0)` — a nice example of using Pydantic constraints for cheap validation.

---

## 4. `backend/services/intent_service.py` — Intent Detection

This module answers one question: **“What does the user want?”** It returns an `IntentResult` used by `routers/chat.py` to decide which action to run.

### 4.1 Dual‑mode architecture

```python
async def detect_intent(message, history) -> IntentResult:
    if os.getenv("OPENAI_API_KEY"):
        return await detect_intent_llm(...)
    return detect_intent_rules(message)
```

- **LLM mode** (preferred): calls `gpt-4o-mini` with `response_format={"type": "json_object"}` so the model must return strict JSON.
- **Rule‑based fallback**: pure Python regex + keyword scan so the app is fully usable offline / without a key.

### 4.2 LLM mode

`_build_system_prompt(template_names)` dynamically embeds the **actual filenames** currently in the `Templates/` folder so the model can only match against real files (prevents hallucinated template names — see CRITICAL RULE #4 in the prompt).

The prompt also contains **explicit CRITICAL RULES** to fix known ambiguities:

- “fetch clients” must be `LIST_CLIENTS`, not `FETCH_TEMPLATE`.
- Abbreviations like `FRD`, `HLD`, `LLD`, `SRS`, `DMP` always mean `FETCH_TEMPLATE`.
- `client_name` only applies to `FETCH_CLIENT_DOCUMENTS` and `UPLOAD_DOCUMENT`.

Last 6 turns of `history` are forwarded to preserve short‑term context. The raw JSON reply is parsed and coerced through `_safe_intent()` / `_safe_float()` helpers so a malformed value never crashes the router — worst case we get `IntentType.UNKNOWN`.

If the LLM call throws (network, quota, invalid JSON), the code **automatically falls back** to `detect_intent_rules()`.

### 4.3 Rule‑based mode

Uses ordered keyword sets and regex patterns. The **order of checks matters** and is carefully commented:

1. `GREETING` (whole‑word match on “hi/hello/…”).
2. `LIST_CLIENTS` — checked **before** `FETCH_TEMPLATE` to avoid “fetch clients” being misread.
3. `UPLOAD_DOCUMENT` / `STORE_DOCUMENT` — checked before `FETCH_CLIENT_DOCUMENTS` so “upload doc for XYZ” isn’t caught by the client‑doc regex.
4. `FETCH_CLIENT_DOCUMENTS` via `_CLIENT_DOC_PATTERNS` (5 regexes that extract the client name from phrases like “documents for XYZ”).
5. `SEARCH_DOCUMENTS`, `LIST_TEMPLATES`.
6. `FETCH_TEMPLATE` — triggered by fetch verbs + doc abbreviations, but explicitly **not** if the word `client` appears (disambiguation).
7. Default → `CLARIFY_INTENT` with a helpful multi‑choice question.

`_extract_client_name_from_message` runs the same regex family plus a `for/from <name>` fallback, filtered through `_CLIENT_STOPWORDS` so words like “template” or “please” are never treated as client names.

---

## 5. `backend/services/storage_service.py` — File System Layer

This is the largest and most important service. It owns **all** filesystem interactions and enforces path‑safety.

### 5.1 Configuration and constants

- `ALLOWED_EXTENSIONS = {.docx, .doc, .pdf, .xlsx, .pptx, .txt}` — enforced on both list and upload.
- `MAX_UPLOAD_SIZE_BYTES = 50 MB`.
- `PROJECT_ROOT`, `TEMPLATES_DIR`, `CLIENTS_DIR` — resolved **once** at import time relative to the module’s own file, so the app works regardless of the current working directory.

### 5.2 The 7‑phase client folder structure

Every client gets a standardized SDLC‑style layout:

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

`_TYPE_TO_SUBFOLDER` is an **ordered** list of (keywords → subfolder) tuples. Order matters: more specific phrases (e.g. `"test summary"`) come before generic ones (e.g. `"test case"`). `_detect_phase_folder()` normalises the combined `document_type + filename`, walks the list, and returns the first match — defaulting to `"1. Pre-requisites"` when nothing matches.

`_create_client_subfolders()` guarantees all 7 phase folders exist whenever a client folder is touched.

### 5.3 Template discovery — `list_templates()`

Instead of hard‑coding template names, this scans `Templates/` on every call and produces a `TemplateInfo` for each valid file, including:

- A human‑friendly `name` from `_display_name_from_filename()` — strips `(QMS-126)`‑style tags, replaces `_`/`-` with spaces.
- A URL‑safe `download_url` using `urllib.parse.quote` on the filename (handles spaces and special chars).
- File size in KB.

This makes the system **zero‑config** for new templates: drop a file into `Templates/` and it appears in the API.

### 5.4 Fuzzy template matching — `find_best_template()`

Combines three signals to score each template against a user query:

1. `difflib.SequenceMatcher` ratio between the normalised query and the template’s searchable text.
2. **Token‑overlap bonus** (`× 1.2`) — crucial for abbreviations. Query tokens are enriched via `_QUERY_PHRASE_TO_ABBREV` (e.g. “high level design” → also add `hld`), and template text is enriched via `_PHRASE_TO_ABBREV` so an abbreviation query can still match a spelled‑out template name.
3. Exact‑substring bonus (`+ 0.7`) and explicit `document_type` bonus (`+ 1.2`).

Only returns a match if the best score is ≥ `minimum_score` (default `0.3`), otherwise `None`.

### 5.5 Client discovery — `_discover_client_locations()`

Supports **two** on‑disk layouts for backwards compatibility:

- **Standard**: `Clients/<name>/…`
- **Legacy / flat**: `Clients_<something>/…` at project root.

Uses `os.path.realpath` in a `seen` set so symlinks / duplicates are de‑duplicated. Returns `(client_name, folder_name, absolute_path)` triples.

`_collect_documents_in_folder()` walks up to **2 subdirectory levels** (safe recursion depth), skips folders it can’t read (`PermissionError`), and produces `DocumentInfo` objects. Results are sorted by `uploaded_at` descending (newest first).

### 5.6 Security — `get_client_file_path()`

Anti‑path‑traversal check for the `/api/documents/client-file` endpoint:

1. Normalises separators and resolves to an absolute path.
2. Rejects anything that does not start with `PROJECT_ROOT + os.sep` (blocks `../../` escapes).
3. Requires the resolved path to live under `CLIENTS_DIR` **or** a legacy `Clients_*` folder.
4. Requires the file to actually exist and have an allowed extension.
5. Logs traversal attempts with `logger.warning`.

Returns `None` on any failure — the router then responds with 404, never leaking why.

### 5.7 Storing an upload — `store_document()`

Called by `POST /api/upload`. Steps:

1. Ensures the client folder + 7 phase subfolders exist.
2. Routes to the correct phase via `_detect_phase_folder(document_type, original_filename)`.
3. Builds a **collision‑proof filename**: `<client>_<type>_<YYYYMMDD_HHMMSS>.<ext>`, using `_sanitize_folder_name()` to strip invalid chars.
4. Uses `shutil.move()` (not `copy`) so the temp file left by the router is cleaned up in the same call.
5. Returns a `DocumentInfo` including a safe relative `download_url`.

### 5.8 Miscellaneous helpers

- `search_documents(query)` — case‑insensitive substring search across filename, client name, and document type across **all** clients.
- `list_client_documents(client_name=None)` — legacy flat list for the `/api/documents` endpoint.
- `detect_doc_type_from_content_or_filename()` — used by `/api/upload/detect-type` to pre‑fill the UI’s document‑type field based on filename heuristics.

---

## 6. `backend/services/chat_service.py` — Reply Generation

Turns an `IntentResult` + an `action_outcome` string (produced by the chat router) into the natural‑language message shown to the user.

### 6.1 Dual‑mode again

Same pattern as intent detection:

- **With `OPENAI_API_KEY`** → `_llm_response()` calls `gpt-4o-mini` with:
  - A persona system prompt (`ASSISTANT_PERSONA` — “MarBot”, professional/friendly, markdown, one clarification question at a time, no invented names).
  - A `[Context: ...]` block containing the intent, entities, and outcome — so the model composes a reply consistent with what the router actually did.
  - The last 6 conversation turns, normalised via `_role_map` (e.g. UI’s `"bot"` role is mapped to OpenAI’s `"assistant"`).
- **Without a key**, or if the LLM call fails → `_rule_based_response()` returns a curated markdown reply per intent (greeting menu, template confirmation, upload prompt, empty‑state messages, etc.).

The router never has to know which path was taken — it just calls `await generate_response(...)`.

---

## 7. Routers — HTTP Surface

### 7.1 `routers/chat.py` — `POST /api/chat`

The orchestrator. Flow:

1. Generate a `session_id` if the client didn’t send one.
2. Reject empty messages with a 400.
3. `detect_intent(...)` → `IntentResult`.
4. **`match intent.intent:`** — Python 3.10 structural pattern matching selects the behaviour:
   - `FETCH_TEMPLATE`: prefer the LLM‑selected `matched_filename` (validated against disk via `get_template_path`), else fuzzy‑match with `find_best_template`. On success, set `action="download"` and a `download_url`. Otherwise return a list of all templates so the UI can render a picker.
   - `LIST_TEMPLATES`: return everything from `list_templates()`.
   - `UPLOAD_DOCUMENT` / `STORE_DOCUMENT`: `action="upload_prompt"` — the frontend opens the upload widget.
   - `LIST_CLIENTS`: return `list_all_clients()`.
   - `FETCH_CLIENT_DOCUMENTS`: `find_client_documents(name)`; on miss, gracefully degrade to the client list.
   - `SEARCH_DOCUMENTS`: forward the raw message to `search_documents(...)`.
   - `GREETING` / `CLARIFY_INTENT` / default: no side effects, just build a message.
5. Compose `bot_message` via `generate_response(...)` using the intent + `action_outcome`.
6. Return a fully populated `ChatResponse`.

Each branch also builds a short `action_outcome` string (“Found 3 clients”, “needs clarification”, …) so the LLM reply can be **grounded** in what really happened.

### 7.2 `routers/templates.py`

- `GET /api/templates/` → list all templates as JSON.
- `GET /api/templates/{doc_type}` → metadata for the best fuzzy match; on miss returns 404 with the full list of alternatives in the error body.
- `GET /api/templates/download/{filename}` → streams the file via `FileResponse` with the correct MIME type. `os.path.basename(filename)` protects against path traversal in the URL.

### 7.3 `routers/upload.py` — `POST /api/upload`

Multipart handler:

1. Requires `client_name` (or `project_name`) and `document_type`.
2. Reads bytes, validates:
   - Filename is present.
   - Extension is in `ALLOWED_EXTENSIONS`.
   - Not empty, not larger than `MAX_UPLOAD_SIZE_MB` (returns HTTP 413 if too big).
3. Writes to a **temp file** in the OS temp dir (`tempfile.gettempdir()`), then calls `store_document(...)` which `shutil.move`s it into the correct client phase folder.
4. On any exception cleans up the temp file, logs the traceback (`logger.exception`), and returns HTTP 500.
5. Also exposes `POST /api/upload/detect-type` to help the frontend pre‑fill the type field.

### 7.4 `routers/documents.py`

- `GET /api/documents/` → all documents, optional `?client=` filter.
- `GET /api/documents/clients` → client list with a friendly empty‑state message.
- `GET /api/documents/search?q=` → substring search.
- `GET /api/documents/client-file?path=` → **safe download** using `get_client_file_path()` (see §5.6). MIME type is guessed via `mimetypes`.
- `GET /api/documents/download?file_path=` → **legacy** absolute‑path download; still validates that the path is inside `PROJECT_ROOT` and exists.

---

## 8. End‑to‑End Request Traces

### 8.1 “Give me the HLD template”

1. `POST /api/chat` with `{message: "Give me the HLD template"}`.
2. `detect_intent()` → LLM returns `{intent: FETCH_TEMPLATE, matched_filename: "Marlabs (QMS-144) High Level Design- DE - Template.docx"}`.
3. `chat.py` validates the filename via `get_template_path()`, finds the matching `TemplateInfo`, sets `action="download"`, `download_url="/api/templates/download/..."`.
4. `chat_service.generate_response()` composes “Here’s your **HLD** template! Click download below…”.
5. Frontend renders a download button that hits `/api/templates/download/<file>`, which streams the `.docx`.

### 8.2 “Upload the FRD for ABCD”

1. Frontend opens the upload modal (triggered by `action="upload_prompt"` from a prior chat turn).
2. `POST /api/upload` with the file, `client_name="ABCD"`, `document_type="FRD"`.
3. `upload.py` validates extension/size, writes to temp.
4. `store_document()` calls `_detect_phase_folder("FRD", filename)` → `"2. Requirement Analysis"`, ensures `Clients/ABCD/2. Requirement Analysis/` exists, renames to `abcd_frd_20260713_101500.docx`, moves it into place.
5. Response includes the new `DocumentInfo` with a safe `download_url`.

### 8.3 “Show me all documents for ABCD”

1. `POST /api/chat` → intent `FETCH_CLIENT_DOCUMENTS`, `client_name="ABCD"`.
2. `find_client_documents("ABCD")` scans both standard and legacy layouts, collects docs (2 levels deep) from `Clients/ABCD/`.
3. Response contains `clients: [ClientInfo(...)]`; the UI renders a list with per‑document download buttons pointing at `/api/documents/client-file?path=...`.

---

## 9. Design Choices Worth Highlighting

- **Zero‑config templates & clients** — everything is discovered from the filesystem on demand, so admins just drop/rename files.
- **LLM with rule‑based fallback** on both intent and reply generation — the app degrades gracefully without an API key or during outages.
- **Grounded LLM prompts** — the intent prompt embeds real template filenames; the reply prompt embeds the actual action outcome. This dramatically reduces hallucination.
- **Enum‑driven control flow** — `IntentType` + `match/case` in the router keep the orchestration readable and exhaustively check‑able.
- **Path‑safety everywhere** — `os.path.basename()`, `startswith(PROJECT_ROOT)`, allowed‑extension checks, and a dedicated `get_client_file_path()` guard against path traversal.
- **Phase‑based storage** — uploads are auto‑routed to the correct SDLC phase folder based on keyword matching against `document_type` + filename.
- **Backwards compatibility** — both the new `Clients/<name>/` layout and the old `Clients_<...>` flat layout are recognised.
- **Session id + short conversation history** — enables multi‑turn dialogs (e.g. clarification questions) without any server‑side state store.

---

## 10. Dependencies (`backend/requirements.txt`)

| Package               | Why                                                        |
|-----------------------|------------------------------------------------------------|
| `fastapi>=0.115`      | Web framework.                                             |
| `uvicorn[standard]`   | ASGI server used to run FastAPI.                           |
| `python-multipart`    | Required for `UploadFile` / `Form` parsing.                |
| `openai>=1.50`        | Async client for GPT‑4o‑mini.                              |
| `pydantic>=2.10`      | Data validation and settings.                              |
| `python-dotenv`       | Load `OPENAI_API_KEY` from `.env` during development.      |
| `aiofiles`            | Async file I/O helper (available for future streaming use).|

Run locally:

```powershell
cd backend
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000/docs` for the interactive Swagger UI and `frontend/index.html` for the chat UI.

---

*Generated as an in‑depth code walkthrough of the `backend/` package. Refer to `README.md` for the higher‑level system design diagrams and setup steps.*
