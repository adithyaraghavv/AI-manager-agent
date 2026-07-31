# Delivery AI Agent — Frontend

Minimal React + Vite chat UI for the Marlabs Delivery Assistant. Talks to the FastAPI
backend in `/backend` (proxied at `/api` and `/health` during dev, see `vite.config.js`).

## Setup

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173, proxies /api and /health to http://localhost:8000
```

The backend must be running on port 8000 (see `/backend/README.md`) — start it first.

## Structure

- `src/App.jsx` — page shell, backend health indicator
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
