# RAG Agent – End-to-End Testing Checklist

Run the server before testing:
```
cd backend
python -m uvicorn main:app --port 8000 --reload
```
Open `frontend/index.html` in Live Server (port 5500) or double-click in a browser.

---

## A. Template Discovery & Download

| # | Action | Expected |
|---|--------|----------|
| A1 | Chat: `list templates` | Sidebar shows 5 template cards (FRD, SRS, HLD, LLD, DMP) |
| A2 | Chat: `FRD` | Download link returned for the FRD `.doc` file |
| A3 | Chat: `HLD` | Download link returned for the HLD `.docx` file |
| A4 | Chat: `SRS` | Download link returned for the SRS `.docx` file |
| A5 | Chat: `LLD` | Download link returned for the LLD `.docx` file |
| A6 | Chat: `DMP` | Download link returned for the DMP `.docx` file |
| A7 | Chat: `give me the FRD template` | FRD download (not SRS) |
| A8 | Chat: `I need a requirements doc` | SRS or FRD download (requirements-related) |
| A9 | Chat: `I need data management plan` | DMP download |
| A10 | Chat: `functional requirements document` | FRD download |
| A11 | Click a Download button in chat | Browser downloads the binary file correctly (not garbled text) |
| A12 | Add a new `.docx` to `Templates/` folder | Appears automatically in next `list templates` without code changes |
| A13 | Request a template that doesn't exist | Bot replies with list of available templates |

---

## B. Client Listing

| # | Action | Expected |
|---|--------|----------|
| B1 | Chat: `list clients` | Client cards rendered; shows folder names and document count |
| B2 | Chat: `fetch clients` | Same as B1 (not misrouted to FETCH_TEMPLATE) |
| B3 | Chat: `what clients do you have` | Same as B1 |
| B4 | Chat: `which clients are active` | Same as B1 |
| B5 | Click "List Clients" sidebar button | Same as B1 |
| B6 | Create `Clients/AcmeCorp/` folder (empty) | AcmeCorp appears in client list with 0 documents |
| B7 | Create `Clients_XYZ_FRD/` at project root | XYZ appears in client list (legacy folder scanning) |

---

## C. Client Documents

| # | Action | Expected |
|---|--------|----------|
| C1 | Chat: `get documents for <ClientName>` | Expandable card with document list and download links |
| C2 | Chat: `docs for <ClientName>` | Same as C1 |
| C3 | Click download link on a client document | Browser downloads the file correctly |
| C4 | Client with no documents | Shows empty document list (no crash) |
| C5 | Unknown client name | Bot shows all clients as fallback |

---

## D. File Upload

| # | Action | Expected |
|---|--------|----------|
| D1 | Upload a `.docx` for a client | Success toast; file appears in `Clients/<name>/` |
| D2 | Upload a `.pdf` | Accepted |
| D3 | Upload a `.exe` | Rejected with "File type not allowed" error |
| D4 | Upload a file > 50 MB | Rejected with "File too large" (413) error |
| D5 | Upload with no client name | Rejected with "Client name required" |
| D6 | Upload with custom document type | Accepted; stored with custom type in filename |
| D7 | After upload, run `list clients` | Uploaded file appears in client's document list |

---

## E. Error Handling

| # | Action | Expected |
|---|--------|----------|
| E1 | Send empty message | 400 error; chat shows friendly message |
| E2 | Request `/api/templates/download/../../etc/passwd` | 404 or 403 (path traversal blocked) |
| E3 | Request `/api/documents/client-file?path=../backend/main.py` | 403/404 (path traversal blocked) |
| E4 | Chat: `hello` | Greeting response, no error |

---

## F. Intent Routing

| # | Message | Expected Intent |
|---|---------|----------------|
| F1 | `hello` | GREETING |
| F2 | `list clients` | LIST_CLIENTS |
| F3 | `get me the FRD template` | FETCH_TEMPLATE → FRD file |
| F4 | `get documents for Marlabs` | FETCH_CLIENT_DOCUMENTS, client=Marlabs |
| F5 | `upload document for Acme` | UPLOAD_DOCUMENT (not FETCH_CLIENT_DOCUMENTS) |
| F6 | `list templates` | LIST_TEMPLATES |
| F7 | `search for requirements` | SEARCH_DOCUMENTS |

---

## G. Frontend UI

| # | Check | Expected |
|---|-------|----------|
| G1 | Page load | Light background (#F8FAFC), dark-blue sidebar (#1E3A8A) |
| G2 | Chat bubbles | User = dark-blue right-aligned; bot = white left-aligned |
| G3 | Template list in chat | Cards with name, size, download button |
| G4 | Client list in chat | Expandable cards showing document rows with download links |
| G5 | Upload modal | Opens on paperclip icon; shows document type dropdown incl. "Other (custom)" |
| G6 | Sidebar "List Clients" button | Sends "list clients" message and renders client cards |
| G7 | Responsive layout | No horizontal scroll on narrow windows |

---

## H. API Endpoints Quick Reference

```
GET  /api/templates                        → list all templates
GET  /api/templates/download/{filename}    → download template file
GET  /api/documents/clients               → list all clients + documents
GET  /api/documents/client-file?path=...  → download a client document
POST /api/chat                             → chat intent + response
POST /api/upload                           → upload a completed document
GET  /health                               → {"status": "ok"}
```
