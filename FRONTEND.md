# DocuBot / MarBot — Frontend Documentation

This document explains **what the frontend does** and **how the code in `frontend/index.html` is structured**. The entire UI is a single self‑contained HTML file: no build step, no `npm install` — just open it in a browser (or serve it statically) and it talks to the FastAPI backend at `http://localhost:8000`.

---

## 1. Functionality Overview

The frontend is **MarBot**, a chat‑first Project Management Document Assistant UI. It gives the user:

### 1.1 Conversational chat
- A ChatGPT‑style message list with **user** and **assistant** bubbles, avatars, timestamps.
- A **typing indicator** while awaiting a backend reply.
- **Markdown rendering** in bubbles: `**bold**`, `` `inline code` ``, bullet lists (`• item`), paragraphs, line breaks — all HTML‑escaped first for XSS safety.
- **Auto‑scroll** to the newest message and an **auto‑growing textarea** input (max 120 px).
- Keyboard: **Enter** to send, **Shift+Enter** for a new line.

### 1.2 Action cards inside chat replies
The backend returns an `action` hint on each `ChatResponse`. The bubble renders a rich card based on it:

| `action` value        | Card rendered                                                                   |
|-----------------------|---------------------------------------------------------------------------------|
| `download`            | **Template Ready** card with a big download button.                             |
| `list_templates`      | Grid of template cards (icon + type + size).                                    |
| `list_clients`        | Collapsible client cards, each with a doc count badge.                          |
| `client_documents`    | Same UI, focused on one client’s documents.                                     |
| `upload_prompt`       | Card with a dark button that opens the upload modal.                            |
| `search_results`      | List of matching docs with per‑row download links.                              |

### 1.3 Sidebar (left rail)
- **Brand** + logo mark.
- **Collapsible “Navigation” section** with quick actions: *All Templates*, *List Clients*, *Upload Document*.
- **Quick Fetch pills** — one pill per document type discovered from the backend, so users can fetch a template with a single click.
- **Recents (chat history)** — every conversation with ≥1 user message is auto‑saved to `localStorage` under key `marbot_chat_history` (max 30). Items can be **loaded** or **deleted** individually.
- **New Chat** button (bottom foot) — resets the conversation.

### 1.4 Top bar
- Brand + AI‑Powered badge.
- A **command palette trigger** (styled as a fake search input) with keyboard shortcut hint `Ctrl K`.
- Icon buttons for **Upload** and **New chat**.

### 1.5 Command palette (Ctrl + K)
- Fuzzy‑filterable list of 8 predefined actions (`List All Templates`, `List Clients`, `Upload Document`, `Fetch FRD/HLD/LLD/SRS/DMP Template`).
- **Recents** section at the top (last 2 used) when the query is empty.
- Full **keyboard control**: `↑ ↓` to navigate, `Enter` to run, `Esc` to close; also closes on backdrop click.

### 1.6 Upload modal
- **Drag & drop zone** with visual highlight during drag; falls back to a hidden `<input type="file">` when clicked.
- Accepts `.docx, .pdf, .xlsx, .pptx, .doc, .txt`.
- Displays selected file name and human‑readable size (B / KB / MB).
- **Client / Project name** required field.
- **Document type** dropdown pre‑populated from the templates fetched on startup, plus an **“Other (custom type)”** escape hatch that reveals a free‑text field.
- Submit button is disabled until all required fields are filled; shows *Uploading…* during the request.
- On success closes itself, fires a success **toast**, and posts a “Document stored successfully!” assistant message into the chat.

### 1.7 Toasts
- Slide‑in bottom‑right notifications, auto‑dismiss after 3.5 s.
- `success` (green left‑border) and `error` (red left‑border) variants.

### 1.8 UX niceties
- Reduced‑motion honoured (`@media (prefers-reduced-motion: reduce)`).
- Mobile fallback: sidebar and command trigger hide below 640 px.
- Custom thin scrollbars.
- Full **focus‑visible outlines** for keyboard users.

---

## 2. Tech Stack — No Build Step

- **React 18** loaded from `esm.sh` as an ES module (`https://esm.sh/react@18?dev`).
- **htm** ([tagged template HTML](https://github.com/developit/htm)) used instead of JSX so the browser can run the code directly — no Babel, no bundler.
- Pure **CSS custom properties** (no framework) drive the whole design system (`:root { --ink, --navy, --sky, … }`).
- **Google Fonts (Inter)** loaded via `<link rel="preconnect">`.
- Talks to the backend at `const BASE = "http://localhost:8000/api"`.

To run: open `frontend/index.html` directly, or serve it with any static server (e.g. `python -m http.server 5500` inside `frontend/`).

---

## 3. File Layout of `index.html`

The single file is divided into three logical parts:

1. **`<style>` block** — the entire design system (tokens, layout, components, animations, responsive rules).
2. **`<div id="root">`** — the React mount point.
3. **`<script type="module">`** — imports React + htm, defines helpers, icons, components, then renders `<App />` into `#root`.

---

## 4. Design System (CSS)

### 4.1 Design tokens (`:root`)
- **Palette**: `--ink` (deep navy), `--navy`, `--sky` (accent cyan), `--mist`/`--fog` (surfaces), grey scale (`--text`, `--text-2`, `--text-3`), semantic `--green`/`--red`.
- **Sidebar‑specific** tokens (`--sidebar-w`, `--sidebar-text`, `--sidebar-hover`, `--sidebar-active`) keep the dark rail cleanly themed.
- **Radii**: `--r`, `--r-sm`, `--r-lg`.
- **Fonts**: `--font` (Inter) and `--mono` (SF Mono / fallbacks).
- **Elevation**: three `--shadow*` levels.

### 4.2 Layout skeleton
```
.app  ── flex, 100vh
├── .sidebar         (fixed width, dark, flex‑column)
└── .chat-area
    ├── .topbar
    ├── .msgs        (flex:1, scrolls)
    └── .input-area  (sticky bottom)
```

### 4.3 Notable component styles

| Class(es)                              | Purpose                                                      |
|----------------------------------------|--------------------------------------------------------------|
| `.nav-toggle`, `.nav-items(.open)`     | Collapsible sidebar section with animated chevron + height.  |
| `.pill`                                | Quick‑fetch chips in the sidebar.                            |
| `.cmd-overlay`, `.cmd-panel`, `.cmd-*` | Command palette (modal card with backdrop blur).             |
| `.msg-row`, `.bubble.user/.bot`        | Chat bubbles (different tail radii + colour per role).       |
| `.typing-dots` + `@keyframes bounce`   | Three‑dot typing indicator.                                  |
| `.card`, `.card-head`, `.card-body`    | Action cards embedded in bot replies.                        |
| `.tpl-grid`, `.tpl-card` + `::before`  | Template grid with a sky‑blue top accent bar on hover.       |
| `.client-card`, `.doc-row`, `.doc-dl`  | Nested client → document list with download buttons.         |
| `.drop-zone(.drag)`                    | Upload drag‑and‑drop area.                                   |
| `.toast.success/.error` + `slide-in`   | Corner toast notifications.                                  |
| `.history-item(.active)`               | Sidebar chat history with hover‑only delete button.          |

### 4.4 Accessibility & motion
- Focus rings via `:focus-visible` + `--sky-glow` box‑shadow on inputs.
- `prefers-reduced-motion` disables all transitions/animations globally.
- ARIA: `aria-expanded`/`aria-controls` on the collapsible nav, `role="menu"`/`menuitem` on nav items.

---

## 5. JavaScript Architecture

### 5.1 Imports & bootstrap
```js
import React, { useState, useEffect, useRef, useMemo } from "https://esm.sh/react@18?dev";
import { createRoot } from "https://esm.sh/react-dom@18/client?dev";
import htm from "https://esm.sh/htm@3";
const html = htm.bind(React.createElement);
const BASE = "http://localhost:8000/api";
```
All JSX‑like snippets are written using `` html`…` `` tagged templates, e.g.
```js
html`<button className="pill" onClick=${fn}>${label}</button>`
```

### 5.2 Icon library — `I`
An object mapping short keys (`doc`, `grid`, `db`, `users`, `upload`, `download`, `search`, `menu`, `chev`, `x`, `send`, `refresh`, `clip`, `bot`, `user`, `check`, `alert`, `msg`) to functions returning inline SVG at a given size — keeps markup tidy and avoids external icon fonts.

### 5.3 localStorage helpers
```js
const HIST_KEY = "marbot_chat_history";
loadHistory()  // returns array from localStorage (safe on parse errors)
saveHistory(h) // persists h.slice(0, 30)
```
Only used by the sidebar chat‑history feature.

### 5.4 Utilities

| Helper            | Purpose                                                                |
|-------------------|------------------------------------------------------------------------|
| `relTime(iso)`    | Human times: “just now”, “5m ago”, “yesterday”.                        |
| `escHtml(v)`      | HTML‑escape user/bot content **before** any markdown replacement.      |
| `renderMd(text)`  | Tiny markdown → HTML: `**bold**`, `` `code` ``, `• bullet`, `\n\n` → `</p><p>`, `\n` → `<br>`. Runs after `escHtml`, so it’s XSS‑safe. |
| `normType(v)`     | Lowercase, strip “template”, collapse non‑alphanumerics — used to compare/route document types. |
| `dispType(v)`     | Canonical short label (`FRD`, `HLD`, `LLD`, `SRS`, `Data Mgmt Plan`, or the raw name). |
| `docIcon(type)`   | Picks an appropriate SVG based on the type (`grid` for HLD, `db` for DMP, else `doc`). |
| `resolveUrl(url)` | Prepends `http://localhost:8000` to any relative backend URL.          |
| `fmtSize(kb)`     | KB below 1024, else MB with one decimal.                               |

### 5.5 API layer — `api`
Thin `fetch` wrappers, all returning parsed JSON, throwing on non‑OK:

- `api.chat(message, history, sessionId)` → `POST /chat/`.
- `api.getTemplates()`                    → `GET  /templates/`.
- `api.uploadDocument(file, client, type)`→ `POST /upload/` as `multipart/form-data`.

On failure the wrappers try to read `.detail` from the error body so the UI can surface the backend’s human message.

### 5.6 Command palette data — `ACTIONS`
A static array of 8 action definitions consumed by both the command palette and the “Recents” section. Each item has `{id, label, sub, icon, msg?, action?}` — `msg` is what to send to the chat backend, `action:"upload"` opens the modal directly.

---

## 6. React Components

### 6.1 `<CmdPalette>`
Props: `open, onClose, onSend, onUpload, recent`.

- Focuses its input on open, resets query/focus state.
- Filters `ACTIONS` with `useMemo` based on lowercase substring match against label + sub.
- Handles `ArrowUp/Down/Enter/Escape` key navigation via `onKey`.
- Renders a **Recents** section (top 2) when the query is empty and shows an empty state when there are no matches.
- Footer shows keyboard hints.

### 6.2 `<SidebarNav>`
Collapsible “Navigation” section with three quick‑action buttons wired to `onSend("list all templates")`, `onSend("list clients")`, and `onUpload()`.

### 6.3 `<SidebarHistory>`
Renders the auto‑saved conversation list. Each row is a two‑line button (title + `relTime`) with an on‑hover delete icon.

### 6.4 `<TypingIndicator>`
Bot bubble containing three animated dots.

### 6.5 `<TplCard>`
Single template tile used inside the `list_templates` grid. Calls `onDl(tpl)` (which opens the direct backend download URL in a new tab).

### 6.6 `<DocRow>`
One row inside a client card / search result. Shows filename (with `title` tooltip for overflow), size + extension, and a download link built from `resolveUrl(doc.download_url)`.

### 6.7 `<ClientCard>`
Collapsible client card (default expanded). Header shows the client name, folder name, doc count badge, and a chevron. Body renders `<DocRow>` for each document, or a friendly “No documents stored yet.” state.

### 6.8 `<MsgBubble>`
The heart of the chat area. Depending on `msg.role` and `msg.action`, it composes:

- Avatar (bot or user).
- Main bubble with markdown‑rendered content via `dangerouslySetInnerHTML` (safe because of `escHtml` in `renderMd`).
- One of the **action cards** (Template Ready / Available Templates / Client Documents / Upload prompt / Search Results).
- Local timestamp (`hh:mm`).

### 6.9 `<UploadModal>`
Local state: `file, client, docType, custom, drag, busy`.

- Drag & drop with `onDragOver`/`onDragLeave`/`onDrop`.
- If `docType === "__custom__"` a “Custom Document Type” field appears; the effective type sent to the API is `custom.trim()`.
- Disabled until file + client + effective type are set; disabled again while `busy`.
- On success calls `onSuccess(result)` with the backend payload.

### 6.10 `<Toast>`
Auto‑dismisses after 3.5 s via a `setTimeout` cleared in the effect’s cleanup. Icon and colour vary by `type`.

---

## 7. `<App>` — Top‑Level State & Wiring

### 7.1 State
| State           | Role                                                      |
|-----------------|-----------------------------------------------------------|
| `messages`      | Full conversation array (starts with a greeting).         |
| `input`         | Current textarea contents.                                |
| `typing`        | Boolean → shows `<TypingIndicator>`.                      |
| `sessionId`     | Server‑issued id (persisted across turns within a chat).  |
| `showUpload`    | Toggles `<UploadModal>`.                                  |
| `showCmd`       | Toggles `<CmdPalette>` (also toggled by Ctrl+K).          |
| `toast`         | Current toast (`{msg, type}` or `null`).                  |
| `templates`     | Loaded once on mount from `/api/templates/`.              |
| `tplLoading`    | Skeleton state for the sidebar pills.                     |
| `recent`        | In‑memory list of last 4 command‑palette actions used.    |
| `chatHistory`   | Persisted list of saved conversations (`localStorage`).   |
| `chatId`        | Id of the currently active saved conversation.            |

Two refs: `scrollRef` (message list, for auto‑scroll) and `chatIdRef` (kept in sync with `chatId` so the autosave effect can read it without re‑running).

### 7.2 Effects
1. **Auto‑scroll** to bottom on every `messages` / `typing` change.
2. **Load templates** once on mount (`loadTemplates()`).
3. **Auto‑save conversation** to `chatHistory` + `localStorage` whenever `messages` changes and contains at least one user message; a fresh `id` is generated on the first user turn.
4. **Global Ctrl+K listener** to open/close the command palette.

### 7.3 Derived data
- `typeOpts = useMemo(...)` — unique `document_type` values from loaded templates, feeds both the sidebar Quick Fetch pills and the upload modal’s type dropdown.

### 7.4 Message flow — `sendMessage(text)`
1. Push a `user` message with a timestamp.
2. Clear the input, set `typing = true`.
3. `await api.chat(text, buildHistory(), sessionId)` — `buildHistory()` sends only the last 12 turns as `{role, content}` to keep the payload small.
4. On success push an `assistant` message that carries the full `action`, `download_url`, `document_type`, `available_templates`, `clients` — so `<MsgBubble>` can render the appropriate card.
5. On error push an assistant message explaining the backend is unreachable.
6. `typing = false` in `finally`.

### 7.5 Template downloads — `onTplDl(tpl)`
Builds the URL (`tpl.download_url` if present, else `/api/templates/download/<encoded filename>`), opens it in a new tab, fires a success toast.

### 7.6 Upload success — `onUploadSuccess(result)`
Closes the modal, shows a toast, and appends a synthetic assistant message summarising the stored file (client, type, filename) — so the conversation naturally reflects the side effect.

### 7.7 Command palette wiring — `cmdSend(msg, item)`
Records the chosen action in `recent` (deduped, capped at 4) and delegates to `sendMessage`.

### 7.8 Chat history controls
- `clearChat()` — reset conversation + `chatIdRef`; start fresh with greeting.
- `loadChat(entry)` — replace `messages` with the saved entry; keeps working with a **new session** (server session id reset).
- `deleteChat(id)` — remove from history + `localStorage`; if it was the active chat, start a new one.

---

## 8. End‑to‑End UX Flows

### 8.1 Fetch a template
1. User clicks the **FRD** pill (or types “FRD”, or opens Ctrl+K → “Fetch FRD Template”).
2. `sendMessage("FRD")` → backend replies with `action: "download"` + `download_url`.
3. `<MsgBubble>` renders a **Template Ready** card; the user clicks the download button — the file streams from `/api/templates/download/...`.

### 8.2 Upload a document
1. User clicks **Upload Document** in the sidebar (or paperclip in the input row, or the `upload_prompt` action card).
2. `<UploadModal>` opens; user drops file, fills client name, picks type, submits.
3. `api.uploadDocument` POSTs `multipart/form-data` to `/api/upload/`.
4. `onUploadSuccess` shows a toast + appends an assistant confirmation to the chat.

### 8.3 Browse a client
1. User types “documents for ABCD” (or clicks **List Clients** and then the client card).
2. Backend replies with `action: "client_documents"` and a populated `clients: [...]` array.
3. `<ClientCard>` renders one collapsible card per client; each `<DocRow>` links to `/api/documents/client-file?path=...`.

### 8.4 Command palette (Ctrl + K)
1. User presses Ctrl+K anywhere → overlay + focused input.
2. Types “hld” → list filters instantly; `↓ ↵` to run.
3. On run the palette closes, the chosen action either sends a chat message or opens the upload modal.

---

## 9. Notable Design Choices

- **No build step** — React + htm from `esm.sh` means the whole UI is one file the user can open directly. Ideal for a small internal tool.
- **Single source of truth for actions** — `ACTIONS` array feeds the palette and Recents; sidebar buttons reuse the same underlying handlers (`sendMessage`, `setUpload`).
- **Server‑driven UI** — the backend’s `action` field decides which card appears; the frontend does not classify intents itself.
- **XSS discipline** — every string that flows into `dangerouslySetInnerHTML` (only in `renderMd`) is first HTML‑escaped.
- **Progressive persistence** — only the chat history is persisted; templates and clients stay live (re‑fetched from the backend), so the UI always reflects the current filesystem state.
- **Keyboard first** — Ctrl+K palette, arrow‑key navigation, Enter‑to‑send, Esc‑to‑close everywhere.
- **Reactive layout** — flex‑based, works down to ~640 px (sidebar hides), and respects `prefers-reduced-motion`.
