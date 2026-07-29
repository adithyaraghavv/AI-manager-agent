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
- `src/components/ChatPanel.jsx` — conversational interface, calls `POST /api/chat`
- `src/components/ToolActivity.jsx` — renders agent tool-call results inline (status checks,
  template allow/block decisions, download links) so gating decisions are visible, not just
  implied by the model's prose
- `src/components/UploadPanel.jsx` — completed-document upload form, calls
  `POST /api/clients/{client}/documents`
- `src/api.js` — thin fetch wrapper for the backend API
