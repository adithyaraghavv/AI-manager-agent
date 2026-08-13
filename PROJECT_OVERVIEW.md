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
   with clients flagged automatically if they've gone quiet mid-phase, plus a
   search box to find any stored document by client, type, or filename.

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
- **Accidental deletions are recoverable.** Deleting a client hides them
  everywhere immediately, but their data is kept for a retention window
  before being permanently purged — a confirm-click mistake isn't instantly
  unrecoverable.

## Features (what's built and working today)

### Chatbot capabilities

The assistant (OpenAI GPT-4o) has ten tools it can call — it can
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
4. **Show a document's version history** — every version ever uploaded for
   a client's document, oldest to newest, with who uploaded it and any
   change comment, plus a download link for each one.
5. **Search for a document type by a loose phrase** — when a PM doesn't know
   or doesn't give the exact document name (e.g. "the test document," which
   genuinely matches several real document types), this returns every real
   match so the assistant can ask a clarifying question instead of guessing
   at an exact name — never picks one on the PM's behalf.
6. **Get a document's storage location** — for when a PM explicitly wants to
   know *where* something is filed (a folder path) rather than getting the
   file itself; a separate, deliberately narrower path from actually
   requesting/downloading a document.
7. **Delete a client** — looks the client up and shows their info, but
   **never deletes anything itself**. It hands off to a confirm/cancel card
   in the UI; only a human clicking "Confirm & delete" actually removes
   anything. Deletion is a **soft delete** — the client is hidden everywhere
   (chat, dashboard, search, uploads) immediately, but their documents,
   database record, and files are kept intact until a routine cleanup
   permanently purges them after a retention window. The AI is not allowed
   to claim a deletion happened — it has no way of knowing whether the human
   confirmed.
8. **Mark a document as not applicable to a client** — for when a document
   genuinely doesn't apply to a specific engagement (e.g. the client already
   handed over finished requirements in the SOW, so "Requirement Analysis"
   documents don't apply). Once marked, the gate stops treating it as
   permanently missing — it counts the same as a filed document for phase
   completion, without ever creating a fake upload record. Only triggers when
   the PM explicitly says something is out of scope — the assistant is
   instructed to never use this as a workaround to bypass a gate the PM
   actually wants respected.
9. **Reverse a not-applicable mark** — for when something previously marked
   not-applicable turns out to apply after all; puts the document back to
   genuinely required/missing.
10. **Summarize a client's SOW** — pulls contract value, start/end dates,
    and a scope summary out of a client's filed SOW so a PM can just ask
    for them instead of opening the document. Runs on-demand (re-reads
    whatever SOW is currently on file every time it's asked, never a
    cached/stale answer) and never invents a value — any field the SOW
    doesn't actually state comes back as "not stated," not a guess.
- Every tool result is re-checked fresh, every time — even if the PM asks
  the exact same thing twice in one conversation. Real state (a fixed file,
  a new upload, a newly filed document) can change between messages, so the
  assistant never answers a repeat question from its own earlier reply.

On top of the tools themselves:
- **Attach-to-upload** — drop a completed file directly into the chat
  (paperclip button, or drag-and-drop anywhere onto the chat window) instead
  of switching to the upload panel; shows an inline confirm-before-upload
  card that pre-fills client/doc-type guesses from the conversation,
  editable before anything is sent.
- **A real greeting on a new chat**, not a menu of clickable suggestion
  prompts — reads as an assistant talking to you, not a form to fill in.
- **Saved, reopenable chat history** — past conversations are saved locally
  and listed in a History dropdown; reopen or delete any of them without
  losing the current one.
- **Knows what it doesn't know** — for portfolio-wide questions it has no
  tool for (e.g. "how many clients do we have"), it points to the Dashboard
  tab instead of just declining, since that tab already answers it better
  than a bare number would.
- Every tool call renders inline in the chat as a visible system-note chip
  (⚙ icon + summary, tinted background so it's clearly distinct from the
  agent's own prose), so gating decisions and lookups are never hidden
  inside the model's words — what the system actually did is always
  visible. This is deliberate: real outcomes (upload succeeded, deletion
  happened) are always generated from actual API responses, never left for
  the AI to narrate in its own words — so it can't ever misreport what
  really happened.
- **Avatars on every message** (person icon for you, a Marlabs-branded
  gradient mark for the agent) and an **animated typing indicator** while
  waiting for a reply — easier to scan a long conversation at a glance.
- **New chat button** — clears the conversation without a page refresh.
- **Human-friendly errors with retry** — a failed request shows a plain
  message instead of a raw technical error, with a Retry button that
  resends the same request without duplicating the message in the thread.

### Everything else

- **Document upload** — file a completed document for a client, either
  through the standalone upload panel or by attaching/dragging a file
  directly into the chat thread (with an inline confirm-before-upload card).
  Validated server-side against a file-type allow-list and a 50MB size cap.
- **Document version history.** Re-uploading a document never overwrites or
  loses the previous one — every upload becomes a new, permanent version
  (v1, v2, v3...), with an optional "uploaded by" name and change comment.
  Every version stays downloadable forever, and an older version can be
  **restored** — which copies its content forward as a brand-new version
  rather than deleting anything, so the full history only ever grows.
  Available both from the Dashboard's document search ("Versions" on any
  result) and by asking the chat assistant, e.g. "show me the versions of
  Hillenbrand's HLD."
- **Document search** — a search box on the Dashboard finds any stored
  document by client name, document type, or filename, with a direct
  download link on each result.
- **Hard-block phase-gating** — enforced in `app/services/document_service.py`,
  independent of the AI agent. Blocks both template requests and uploads if
  any earlier phase is incomplete, and reports exactly what's missing.
- **Manager dashboard** (`/api/clients/status`) — every client's phase
  progress, current blocking phase + missing documents, and a stale-client
  flag, with a copy-to-clipboard follow-up reminder generator.
- **Real Marlabs template files** for SRS, HLD, and LLD (sourced from the
  team's existing template library) — everything else still uses a
  placeholder file until a real one is available (see Pending, below).
- **Marlabs branding** — real Marlabs logo, brand colors (navy `#283B91` /
  blue `#0EA5E9`, sampled from the actual logo file), dark navy hero banner,
  and Poppins headings (Google Fonts), styled to match Marlabs' existing
  internal tools. Header and hero span the full browser width; content area
  stays capped at a readable width.
- **One-command local dev** — `npm run dev` from `/frontend` starts both the
  backend and frontend together (via `concurrently`), instead of needing two
  terminals.

## What's set up vs. still pending

### Set up and working
- Backend (FastAPI) + frontend (React/Vite) fully built and integrated
- Supabase Postgres database (via REST API, not a direct connection — works
  even on networks that block direct DB ports)
- Phase-gating logic, fully tested
- Chat agent wired to OpenAI (GPT-4o)
- Document upload/download flow, tested end-to-end, with file-type/size
  validation
- Document search across all stored documents, with download links
- Manager dashboard + stale flagging + copy-reminder feature
- Client deletion via chat, gated behind a mandatory human confirm/cancel
  card — soft-delete (recoverable for a retention window), not instant/
  permanent; a manual cleanup command (`app/db/cleanup_deleted_clients.py`)
  purges anything past that window (not yet on an automatic schedule — see
  Pending)
- Case-insensitive client-name matching everywhere (status, upload, template
  requests, deletion) — fixed after a real bug where differently-cased
  lookups of the same client were treated as two different clients
- Marlabs rebrand (logo, colors, typography)
- Saved/reopenable chat history, drag-and-drop file attach, message
  avatars + animated typing indicator
- 164 backend tests passing, no known dependency CVEs (checked via
  `pip-audit` / `npm audit`)

### Pending
- **Real SharePoint integration.** Templates and client documents currently
  live in a **local filesystem mock** (`/templates`, `/clients`). SRS, HLD,
  and LLD now use real Marlabs template files; everything else is still a
  placeholder `.txt` file. A teammate has already built related work in
  Azure DevOps with existing SharePoint access — a sync is planned to
  reconcile what exists before building `SharePointStorage` (the storage
  backend is already abstracted behind an interface, so swapping it in later
  needs no changes to gating or service logic — see
  `backend/app/storage/base.py`).
- **No authentication on any endpoint.** Every API route is currently open —
  fine for local dev and controlled demos, but must be addressed (at minimum
  a shared API key) before this is reachable by anyone outside a trusted
  network, and definitely before real client documents flow through it
  regularly. This matters more now than before: a document-download route
  was added (previously only template files were downloadable this way; now
  real uploaded client documents are too).
- **Soft-delete cleanup isn't on an automatic schedule yet.** The purge
  command exists and works, but currently has to be run by hand (or wired to
  a cron job/scheduled task later) — it doesn't run itself.
- **FRD and Data Management Plan templates** — real files for these exist in
  the team's Azure DevOps library, but don't map cleanly to any of our
  defined document types. Left out rather than guess a mapping; open
  decision for the team (map FRD → BRD? add DMP as a new document type?).
- **No rate limiting** — relevant once the app is reachable by more than a
  handful of trusted users, since `/api/chat` calls a paid OpenAI API per
  request.

## Tech stack

**Backend**
- Python 3.11, [FastAPI](https://fastapi.tiangolo.com/) — REST API
- [OpenAI](https://platform.openai.com/) (GPT-4o) — the conversational agent's LLM,
  via function-calling tools
- [Supabase](https://supabase.com/) (managed Postgres) — data storage,
  accessed at runtime via its REST API (`httpx`), not a direct DB connection
  (see `backend/README.md`, "Two ways to reach Supabase")
- SQLAlchemy + Alembic — used only for schema migrations, not the running
  app; one-off seed/cleanup scripts also use the REST API (not a direct
  connection) so they can be run from any network
- Pydantic / pydantic-settings — request/response models, config
- pytest — 164 tests covering gating logic, services, routes, and the seed
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

**Prerequisites:** Python 3.11+, Node 18+, git.

**Step 0 — clone the repo:**
```bash
git clone https://github.com/Marlabs-Innovations-Private-Limited/RAG-agent.git
cd RAG-agent
git checkout pullingado
```
Open the folder in your editor before continuing.

**Step 1 — get your credentials first.** You need three things before
anything will run:
- An `OPENAI_API_KEY` (ask whoever holds the team's OpenAI account for one —
  do not reuse a key someone pastes in chat; if one is ever shared that way,
  treat it as compromised and get a fresh one)
- `SUPABASE_URL` and `SUPABASE_KEY` (the `service_role` key, not `anon`) —
  ask a teammate who already has access to the shared Supabase project for
  these; everyone points at the same database, so these don't change per
  person
- (Only if you'll run migrations/seed scripts) a `DATABASE_URL` — see
  `backend/.env.example` for the exact format and a note on which connection
  string to use if your network blocks direct database ports

**Step 2 — one-time backend setup**, from the `backend/` folder:
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
```
Now open `.env` (not `.env.example`) in your editor and fill in the three
values from Step 1. **This file is never committed to git** — every person
has their own local copy, and it must exist before the backend will boot.

Then, still from `backend/`:
```bash
alembic upgrade head
python -m app.db.seed
python -m app.db.seed_templates
```
The last command is easy to skip and causes the most common first-run
error — if you ever see "template is on record but its file isn't set up
on this environment yet," it means this step was skipped; just run it and
retry.

**Step 3 — one-time frontend setup:**
```bash
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

**Step 4 — confirm it's actually working:** type something like "list phases"
or "what's the status for Hillenbrand" into the chat box. A reply back from
the assistant means the whole chain (frontend → backend → Supabase → OpenAI)
is wired up correctly.

**If something still won't start:**
- `ModuleNotFoundError` → you skipped `pip install -r requirements.txt`
  (or it needs re-running after a pull that changed `requirements.txt`)
- Backend won't boot / crashes on startup → `.env` is missing or a value in
  it is blank; double check `OPENAI_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`
- A file-not-found error when requesting a template/document → run
  `python -m app.db.seed_templates` (see Step 2)
- Port 8000 or 5173 already in use (common on Windows after a previous
  `npm run dev` didn't fully stop) → fully close and reopen your editor,
  which kills any leftover background process, then try again

See `backend/README.md` and `frontend/README.md` for more detail, including
why Supabase is accessed two different ways, and `docs/` for the original
discovery documentation and database structure.

## Recent updates

### 2026-08-13 11:50 UTC — Remove inert settings icon from sidebar

- The sidebar's profile footer had a settings gear icon that didn't do
  anything when clicked — no real settings/access-control system exists
  yet (that's item #8, still on hold pending the team's input), so the
  icon just looked broken rather than "coming soon." Removed it; the
  profile footer now shows only the avatar and "Marlabs PM" label, no
  dead click target.

### 2026-08-13 11:20 UTC — Claude-style chat layout (sidebar + conversation history)

Frontend-only redesign — no backend, API, or business-logic changes.

- **Removed the standalone "File a completed document" panel** from the
  right side of the chat screen (`UploadPanel.jsx` deleted). Filing a
  document is still fully supported via the existing attach-to-upload flow
  (paperclip icon or drag-and-drop into the chat) — that flow only ever
  captured client name + doc type, so no upload capability was lost,
  though the standalone panel's optional "uploaded by" / "what changed"
  fields go away with it (nothing in the attach flow captured those
  either, so this wasn't a second path to lose).
- **New permanent left sidebar** (`Sidebar.jsx`): a prominent "+ New chat"
  button, saved conversations grouped by Today / Yesterday / Previous 7
  Days / Previous 30 Days, hover-revealed per-chat menu (Rename, Delete),
  and a profile footer. The profile footer is a placeholder (static
  "Marlabs PM" label, inert settings icon) — there's no real user identity
  system yet; that's item #8 (access control) from the demo feedback,
  still on hold pending the team's input.
- **Conversation state moved up to `App.jsx`** so the sidebar and the chat
  panel can share one active conversation — `ChatPanel` now receives
  `messages`/`setMessages` as props instead of owning them, everything
  else (sending, drag/drop, upload/delete confirm flows) is unchanged.
- **Editable chat title** at the top of the chat panel, synced with the
  sidebar's entry name in both directions.
- Chat column and composer capped at 900px and centered; message spacing
  and composer are otherwise the same as before.
- **Responsive**: sidebar is permanently docked on desktop (with a
  collapse toggle), and becomes a slide-out drawer below 900px width
  (tablet and mobile share one drawer behavior), opened via a hamburger
  button in the header.
- Colors/typography are unchanged — kept the existing Marlabs navy/blue
  design-token system rather than switching to a generic beige palette,
  by explicit choice, to preserve the branding work already shown to
  stakeholders.
- Verified live in a browser at desktop, collapsed-desktop, and mobile
  (drawer open/closed) — rename, delete, new chat, and Dashboard
  navigation all confirmed working. Backend test suite untouched: 164
  passing (no backend files were touched by this change).

### 2026-08-13 09:15 UTC — SOW metadata extraction

- **New chat tool: `get_sow_summary`.** Item #7 from the Aug 11 demo
  feedback: SOWs just sat there as files — nobody could quickly answer
  "what's the contract value for this client" or "when does this
  engagement end" without opening the document and reading it manually.
- A PM can now ask directly (e.g. "what's the contract value for Acme,"
  "when does Acme's engagement end," "what's in scope for Acme") and the
  assistant reads the client's filed SOW and pulls out contract value,
  start date, end date, and a scope summary via GPT-4o. Any field the SOW
  doesn't actually state comes back null — the assistant is told never to
  fill in a guess for a null field.
- Scoped to SOW only (not every document type) — that's the one document
  with a clean, consistent set of facts worth extracting; other document
  types don't have an equivalent structured "facts" ask behind them.
- On-demand only, by design: extraction runs fresh every time it's asked
  (no automatic extraction on upload, no stale cached answer) — same
  "never trust an earlier result" principle the rest of the assistant
  already follows. The result is still cached in a new `sow_metadata`
  table (overwritten on each re-extraction) so it's available for
  anything that wants to query it directly later.
- New `app/core/text_extraction.py` — best-effort plain-text extraction
  from `.txt`, `.pdf`, and `.docx` files (the formats worth the added
  dependency weight; `.doc`/`.xlsx`/`.pptx` report as unsupported rather
  than guessed at). Any parse failure — a corrupted file, or a scanned
  image-only PDF with no text layer — returns "couldn't read this" rather
  than crashing; a malformed PDF can trip a low-level panic in pypdf's
  crypto dependency that a normal `except Exception` doesn't even catch,
  so that path is deliberately guarded against too.
- New table `sow_metadata` (migration `d8a3f5c1e6b7`), new dependencies
  `pypdf`, `python-docx`, `cffi`.
- Live-testing fix: a plain "summarize the SOW" (no specific field named)
  was only surfacing the scope field, since the tool's examples were all
  field-specific questions. A general summary/overview request now
  explicitly triggers all four fields together (value, both dates, scope)
  instead of the assistant picking one arbitrarily.
- 164 backend tests passing (was 148).

### 2026-08-12 13:40 UTC — Phase/document "not applicable" flag

- **New chat tools: `mark_document_not_applicable` and
  `unmark_document_not_applicable`.** Item #6 from the Aug 11 demo feedback:
  some documents genuinely don't apply to a specific client's engagement
  (e.g. the client already handed over finished requirements inside the SOW,
  so a separate "Requirement Analysis" document doesn't apply). Before this,
  a document like that would sit "missing" forever and permanently block
  every later phase — there was no way to tell the gate "this one doesn't
  count."
- A PM can now say something like "Requirement Analysis doesn't apply here,
  the client gave us finished requirements in the SOW," and the assistant
  marks it. From then on the gate treats it exactly like a filed document —
  it stops blocking later phases — without ever creating a fake upload
  record. `unmark_document_not_applicable` reverses it if it turns out the
  document does apply after all.
- Guardrail baked into the system prompt: this is only for when the PM
  explicitly says something is out of scope. The assistant is told never to
  reach for it as a workaround just because a request got blocked or a
  document hasn't been filed yet — that would quietly defeat the hard gate
  it's supposed to respect.
- `get_client_status` now reports three states per phase instead of two:
  filed, genuinely missing, and not-applicable — shown separately so a PM
  can see at a glance what's actually blocking them versus what's been
  waived.
- New table `not_applicable_documents` (migration `c7f2a1e9d3b4`), and a new
  `satisfied_document_types` helper (filed ∪ not-applicable) that both
  `request_template` and `upload_document` now check against instead of
  filed documents alone.
- New tests across client-service logic, a document-service integration
  test for both marking and unmarking, agent-tool dispatch, and
  system-prompt guardrail regressions — 146 backend tests passing (was 134
  before this feature).

### 2026-08-12 12:19 UTC — Path-only document lookups

- **New chat tool: `get_document_location`.** From the same demo feedback
  as guided discovery: "not everything needs to be a downloadable file — a
  folder path is sometimes enough." When a PM explicitly asks where
  something is stored ("where is the SOW", "just the path, don't download
  it") the agent now returns the folder path instead of a download link —
  a deliberately separate, narrower path from an ordinary "give me X"
  request, which still hands over the actual file exactly as before.
  Rendered in chat as a quiet path card (monospace path + copy button),
  visually distinct from the file-card download UI so it doesn't read as
  "another download option."
- 133 backend tests passing (was 127).

### 2026-08-12 11:01 UTC — Guided document discovery

- **New chat tool: `search_document_types`.** From the Aug 11 demo feedback
  (Hames): a PM who doesn't know the exact document name — e.g. just says
  "the test document" — should get a conversational narrowing instead of a
  failed exact-match lookup. The tool searches every real document type by
  a loose/partial phrase; a query like "test" genuinely matches 4 different
  document types across 2 phases in the standard config, and the agent is
  now required to list all matches and ask which one the PM means rather
  than guessing at one. Single-match queries resolve directly, no
  clarifying question needed.
- New pure-logic module `app/core/document_lookup.py` (`find_document_types`)
  — no DB/network dependency, so it's fast and trivially testable.
- 127 backend tests passing (was 117).

### 2026-08-11 10:14 UTC — Chat UI overhaul, agent reliability fixes, viewport-scroll fix

- **Two more live agent bugs fixed**, found during the same pre-demo testing pass as the stale-answer fix below:
  - The assistant fabricated fake download links (e.g. `sandbox:/api/...`) instead of calling a tool and using its real `download_url` when asked for one directly. System prompt now explicitly forbids inventing any link under any circumstance.
  - Casual document-type phrasing ("signed off test summary report") didn't match the config's exact spelling ("Signed-off Test Summary Report") and was wrongly reported as undefined. System prompt now requires resolving to the exact string from `list_phases` rather than guessing/paraphrasing.
- **Tone pass.** The system prompt's "not a chatty assistant" instruction was producing stiff, clipped replies — replaced with guidance toward natural, warm, Claude/ChatGPT-style phrasing while keeping the same accuracy requirements. The static new-chat greeting (not AI-generated) was rewritten to match.
- **Chat UI redesign** (three passes, driven by live demo feedback):
  - Removed "YOU"/"AGENT" labels and repeated avatars — consecutive messages from the same sender now group under one avatar.
  - Widened the message column to use the panel's actual available width (was artificially capped, leaving dead gutters); differentiated bubble widths (user 58% / assistant 72%); tightened spacing to an 8/12/20px rhythm.
  - Replaced the generic robot avatar with a Marlabs-branded gradient "M" mark.
  - Every downloadable file (a template, a document version) now renders as a real file card — icon, title, version badge, uploader/comment, download button, hover lift — instead of a bare text link.
  - `get_client_status` now renders as a status card (progress bar + blocking detail) instead of one dense sentence.
  - Added hover-to-copy on messages, a brief "in progress" phase before a tool result settles (spinner + present-continuous phrasing, e.g. "Checking status for..."), a soft elevation shadow on the chat panel, a modern thin scrollbar, and Inter for message typography (alongside the existing Poppins headings).
  - Composer shrunk and now genuinely auto-grows/shrinks with content instead of a fixed single row.
- **Fixed page-level scrolling.** The whole page was scrolling instead of just the chat messages — root cause was `.app` using `min-height` (not a fixed height) plus the upload panel using `height: fit-content` inside an auto-sized grid row, so the panel's stacked form fields pushed the entire page taller than the viewport. Fixed by pinning the page to `100svh` with no page-level scroll, and having the chat panel, upload panel, and dashboard each fill their own space with their own internal `overflow-y: auto` — header, tabs, and the composer now stay visible together at all times on common laptop screens.
- 117 backend tests passing (frontend-only changes beyond this point didn't add backend tests).

### 2026-08-11 — Document version history, fixed a live stale-answer bug

- **Document version history added.** Re-uploading a document no longer
  overwrites the previous file — every upload creates a new, permanent
  version (new `document_versions` table, one immutable row per upload),
  with an optional uploader name and change comment. `client_documents`
  still tracks only the current version (so gating logic is unchanged), but
  every past version stays downloadable, viewable, and can be **restored**
  (which copies its content forward as a brand-new version — nothing is
  ever deleted or overwritten). Reachable from the Dashboard's document
  search ("Versions" on any result) and from the chat assistant (new
  `get_document_versions` tool). While building this, a real bug was
  caught by the test suite before it shipped: two uploads within the same
  second would have collided on the same filename and silently overwritten
  each other on disk despite getting separate version numbers in the
  database — fixed by folding the version number into the storage path
  instead of relying on timestamp precision alone.
- **Fixed a live bug found during pre-demo testing:** within a single chat
  conversation, asking for the same template/status a second time could
  return the model's memory of its earlier answer instead of re-checking —
  so a file that had since been fixed still reported as broken. The system
  prompt now explicitly requires every request to call the tool again,
  since real state (files, uploads, phase status) can change between
  messages and a past tool result is never guaranteed to still be accurate.
- 113 backend tests passing.

### 2026-08-07 — Friendly error for missing local template files, LLM swapped from Groq to OpenAI

- Fresh-clone crash fixed: requesting a template or an already-uploaded
  document whose database record exists but whose file was never seeded
  locally (fresh clone, `seed_templates` never run there) now returns a
  clear, actionable error (`TemplateFileMissing` / enhanced
  `ClientDocumentNotFound`) instead of a raw `FileNotFoundError` / 500.
  Wired through the REST download routes (503) and the chat tool dispatch.
- Swapped the conversational agent's LLM provider from Groq (Llama 3.3 70B,
  free-tier 100k-tokens/day cap) to OpenAI (GPT-4o) to remove the daily
  rate-limit ceiling hit during testing. `OPENAI_API_KEY` replaces
  `GROQ_API_KEY` everywhere (config, `.env.example`, requirements). The
  Groq-specific `tool_use_failed` retry hack was removed since it doesn't
  apply to OpenAI's tool-calling.
- 91 backend tests passing.

### 2026-08-07 07:19 UTC — ADO codebase merged in, `pullingado` branch, PR opened

The team's Azure DevOps "RAG Agent" codebase was imported (frozen, untouched,
on the `ado-import` branch) and compared feature-by-feature against this
app. The two are different products, not one being a newer version of the
other — the ADO version has no phase-gating and no database, ours does both.
The genuinely useful pieces from their side were pulled into this app on a
new `pullingado` branch, which also picked up several fixes and additions
from live review/testing:

- Real Marlabs template files for SRS/HLD/LLD (from the ADO team's library)
- Upload file-type/size validation (previously unenforced)
- Saved/reopenable chat history, drag-and-drop file attach
- Empty-chat greeting instead of clickable suggestion chips
- Message avatars, animated typing indicator, tool-activity chips styled as
  system notes instead of bare text
- Document search across all stored documents, with download links (found
  and fixed a filter-injection bug in the search query during testing)
- Client deletion changed from instant/permanent to soft-delete with a
  retention window, plus a manual purge command for the actual cleanup
- `pullingado` and `ado-import` both pushed to the Marlabs org repo
  (`Marlabs-Innovations-Private-Limited/RAG-agent`) as `main` and
  `pullingado`; PR #1 opened proposing `pullingado` replace `main`, under
  review by the team as of this update
