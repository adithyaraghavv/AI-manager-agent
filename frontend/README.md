# Delivery AI Agent — Frontend

Minimal React + Vite chat UI for the Marlabs Delivery Assistant. Talks to the FastAPI
backend in `/backend` (proxied at `/api` and `/health` during dev, see `vite.config.js`).

## Setup

One-time: install both sides' dependencies, and set up `backend/.env` per `/backend/README.md`
(OPENAI_API_KEY, SUPABASE_URL, SUPABASE_KEY — the backend won't boot without these).

```bash
cd frontend
npm install
cd ../backend
pip install -r requirements.txt
```

Then, every time you want to run it:

```bash
cd frontend
npm run dev   # starts BOTH backend (port 8000) and frontend (port 5173) together
```

`npm run dev` runs the backend and frontend concurrently in one terminal (labeled `[backend]`/
`[frontend]`, color-coded) via the `concurrently` package — no need to open two terminals or start
the backend separately. Ctrl+C (or either process crashing) stops both, no orphaned server left
running. If you want just one side running on its own — e.g. iterating on the backend without
restarting Vite — use `npm run dev:backend` or `npm run dev:frontend` instead.

## Structure

- `src/App.jsx` — page shell, backend health indicator, tab switcher between Chat and Dashboard
- `src/components/Dashboard.jsx` — manager/PM-lead view: every client's phase progress, current
  blocking phase, and a stale flag (⚠, icon+label — status color is never used alone) for clients
  with no activity in `stale_after_days` (backend config, default 3). Calls `GET /api/clients/status`.
- `src/hooks/usePhases.js` + `src/components/DocTypeSelect.jsx` — shared dropdown of exact valid
  document types (grouped by phase), used by both upload paths so a PM never has to type/guess
  the exact config string.
- `src/components/ChatPanel.jsx` — conversational interface, calls `POST /api/chat`. Also has a
  📎 attach button so a PM can hand over a completed document without leaving the conversation —
  see below.
- `src/components/AttachUploadCard.jsx` — the inline confirm-before-upload card that appears in
  the chat thread after attaching a file. Pre-fills client name/document type by reading the
  arguments of recent tool calls in the conversation (pure UX convenience — the PM still confirms/
  edits before anything uploads, so a wrong guess can't cause a wrong upload).
- `src/components/UploadResult.jsx` — renders the upload outcome (success or blocked/error)
  inline in the chat thread, same visual language as `ToolActivity`.
- `src/components/ToolActivity.jsx` — renders agent tool-call results inline (status checks,
  template allow/block decisions, download links) so gating decisions are visible, not just
  implied by the model's prose.
- `src/components/UploadPanel.jsx` — the original standalone upload form (client name/doc type/
  file fields), still available as an alternative to attaching within the chat. Both call the
  same `POST /api/clients/{client}/documents` endpoint — attaching in chat is not a separate
  upload path, just a different way to reach the same one.
- `src/api.js` — thin fetch wrapper for the backend API

Note on the attach flow: the file itself never goes through the AI model — only the chat
*conversation* does. Attaching a file goes straight to the upload REST endpoint, same as the
standalone panel; the model just gets to see the resulting outcome (filed / blocked) like any
other tool result. This was a deliberate choice, not an oversight — pushing binary content through
an LLM tool-call would be wasteful and isn't necessary for the gating decision to work correctly.
