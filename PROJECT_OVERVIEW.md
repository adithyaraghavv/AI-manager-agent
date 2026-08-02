# AI Manager Agent — Project Overview

## What this is

An internal Marlabs tool that helps a delivery manager (or PM) track client
projects through a fixed 7-phase document lifecycle — Pre-requisites,
Requirement Analysis, System Design, Implementation, Testing, Deployment,
Maintenance — without anyone accidentally skipping a required document or
losing track of who's stuck where.

It's two things in one app:

1. **A conversational assistant** — a PM can ask in plain English for a
   template, check a client's status, or upload a completed document.
2. **A manager dashboard** — a portfolio-level view of every client at once,
   with clients flagged automatically if they've gone quiet mid-phase.

The core rule the whole system is built around: **a document belonging to
phase N can't be requested or filed until every required document from every
earlier phase already exists for that client.** This is enforced as a hard
block in the backend, not a suggestion — the conversational agent can't talk
its way around it, because the check happens in the API layer regardless of
what the AI says.

## Why it's helpful to a manager

- **Nothing slips through by accident.** The gating is automatic and
  server-enforced — no relying on someone remembering to check a checklist
  before handing over the next phase's paperwork.
- **One place to see the whole portfolio.** Instead of asking each PM
  individually "where's client X at," the dashboard shows every client's
  phase progress, current blocking phase, and exactly what's missing, at a
  glance.
- **Stale clients get flagged automatically.** If a client's been stuck
  mid-phase with no activity for a few days (configurable, default 3), it's
  flagged on the dashboard — no manual follow-up tracking needed.
- **One-click follow-up.** A "Copy reminder" button on stale clients
  generates a ready-to-send follow-up message (client name, what's missing,
  how long it's been) — copy, paste into email/Slack, send. Nothing is
  auto-sent; a human always reviews and sends it.
- **Consistent file naming and filing**, automatically —
  `Marlabs_<DocType>_<ClientName>_<Timestamp>`, filed under the right client/
  phase folder every time, no manual naming conventions to remember.

## Features (what's built and working today)

### Chatbot capabilities

The assistant (Groq-hosted Llama 3.3 70B) has four tools it can call — it can
only ever do what these tools allow, nothing else, so it can't be talked into
doing something the system doesn't actually support:

1. **List phases** — all 7 phases and the exact documents required for each.
2. **Check a client's status** — which documents exist, which are missing,
   and which phase they're currently blocked on. Client name matching is
   case-insensitive ("Hillenbrand" and "hillenbrand" are the same client,
   never treated as two).
3. **Request a master template** — hard-gated: refuses and explains exactly
   what's missing if any earlier phase is incomplete, rather than handing
   over a template out of order.
4. **Delete a client** — looks the client up and shows their info, but
   **never deletes anything itself**. It hands off to a confirm/cancel card
   in the UI; only a human clicking "Confirm & delete" actually removes
   anything (their documents, database record, and storage folder). The AI
   is not allowed to claim a deletion happened — it has no way of knowing
   whether the human confirmed.

On top of the tools themselves:
- **Attach-to-upload** — drop a completed file directly into the chat
  (paperclip button) instead of switching to the upload panel; shows an
  inline confirm-before-upload card that pre-fills client/doc-type guesses
  from the conversation, editable before anything is sent.
- **Clickable suggested prompts** on the empty chat screen — one click sends
  a real example question instead of typing from scratch.
- **Knows what it doesn't know** — for portfolio-wide questions it has no
  tool for (e.g. "how many clients do we have"), it points to the Dashboard
  tab instead of just declining, since that tab already answers it better
  than a bare number would.
- Every tool call renders inline in the chat as a visible activity line (⚙
  icon + summary), so gating decisions and lookups are never hidden inside
  the model's prose — what the system actually did is always visible.

### Everything else

- **Document upload** — file a completed document for a client, either
  through the standalone upload panel or by attaching a file directly in the
  chat thread (with an inline confirm-before-upload card).
- **Hard-block phase-gating** — enforced in `app/services/document_service.py`,
  independent of the AI agent. Blocks both template requests and uploads if
  any earlier phase is incomplete, and reports exactly what's missing.
- **Manager dashboard** (`/api/clients/status`) — every client's phase
  progress, current blocking phase + missing documents, and a stale-client
  flag, with a copy-to-clipboard follow-up reminder generator.
- **Marlabs branding** — real Marlabs logo, brand colors (navy `#283B91` /
  blue `#0EA5E9`, sampled from the actual logo file), dark navy hero banner,
  and Poppins headings, styled to match Marlabs' existing internal tools.
- **One-command local dev** — `npm run dev` from `/frontend` starts both the
  backend and frontend together (via `concurrently`), instead of needing two
  terminals.

## What's set up vs. still pending

### Set up and working
- Backend (FastAPI) + frontend (React/Vite) fully built and integrated
- Supabase Postgres database (via REST API, not a direct connection — works
  even on networks that block direct DB ports)
- Phase-gating logic, fully tested
- Chat agent wired to Groq
- Document upload/download flow, tested end-to-end
- Manager dashboard + stale flagging + copy-reminder feature
- Client deletion via chat, gated behind a mandatory human confirm/cancel
  card — the AI can propose, only a human click actually deletes
- Case-insensitive client-name matching everywhere (status, upload, template
  requests, deletion) — fixed after a real bug where differently-cased
  lookups of the same client were treated as two different clients
- Marlabs rebrand (logo, colors, typography)
- 67 backend tests passing, no known dependency CVEs (checked via `pip-audit`
  / `npm audit`)

### Pending
- **Real SharePoint integration.** Templates and client documents currently
  live in a **local filesystem mock** (`/templates`, `/clients` — placeholder
  `.txt` files standing in for real Marlabs templates), not real SharePoint.
  A teammate has already built related work in Azure DevOps with existing
  SharePoint access — a sync is planned to reconcile what exists before
  building `SharePointStorage` (the storage backend is already abstracted
  behind an interface, so swapping it in later needs no changes to gating or
  service logic — see `backend/app/storage/base.py`).
- **No authentication on any endpoint.** Every API route is currently open —
  fine for local dev and controlled demos, but must be addressed (at minimum
  a shared API key) before this is reachable by anyone outside a trusted
  network, and definitely before real client documents flow through it
  regularly.
- **No upload file-size limit or file-type allow-list** — worth adding once
  real documents (not mock `.txt` files) are flowing through the system.
- **No rate limiting** — relevant once the app is reachable by more than a
  handful of trusted users, since `/api/chat` calls a paid Groq API per
  request.

## Tech stack

**Backend**
- Python 3.11, [FastAPI](https://fastapi.tiangolo.com/) — REST API
- [Groq](https://groq.com/) (Llama 3.3 70B) — the conversational agent's LLM,
  via function-calling tools
- [Supabase](https://supabase.com/) (managed Postgres) — data storage,
  accessed at runtime via its REST API (`httpx`), not a direct DB connection
  (see `backend/README.md`, "Two ways to reach Supabase")
- SQLAlchemy + Alembic — used only for schema migrations and one-off seed
  scripts, not the running app
- Pydantic / pydantic-settings — request/response models, config
- pytest — 67 tests covering gating logic, services, routes, and the seed
  scripts

**Frontend**
- React 19 + [Vite](https://vitejs.dev/) — no TypeScript, no Tailwind, no
  component framework; plain JS + hand-written CSS
- Plain `fetch` calls to the backend (`src/api.js`), no state-management
  library needed for an app this size

**Storage**
- Abstracted behind `StorageBackend` (`backend/app/storage/base.py`) —
  currently `LocalFilesystemStorage`, designed to be swapped for a
  `SharePointStorage` implementation (via Microsoft Graph API) later with no
  changes to any calling code.

## How to run it locally

**One-time setup:**
```bash
# Backend
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in GROQ_API_KEY, SUPABASE_URL, SUPABASE_KEY
alembic upgrade head
python -m app.db.seed
python -m app.db.seed_templates   # mock template library

# Frontend
cd ../frontend
npm install
```

**Every time after that**, from `/frontend`:
```bash
npm run dev
```
This starts both the backend (port 8000) and frontend (port 5173) together
in one terminal. Open `http://localhost:5173`.

To run either side alone: `npm run dev:backend` or `npm run dev:frontend`.

See `backend/README.md` and `frontend/README.md` for more detail, including
why Supabase is accessed two different ways, and `docs/` for the original
discovery documentation and database structure.
