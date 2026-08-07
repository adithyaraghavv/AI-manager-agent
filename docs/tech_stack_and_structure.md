# Tech Stack & Project Structure — Delivery AI Agent (Greenfield Build)

## Decisions

- **Retrieval:** structured lookup, not RAG. The LLM is used only for conversational intent parsing (tool-calling), resolved against DB queries seeded from `sdlc_phase_config.json`.
- **Database:** PostgreSQL (Supabase-hosted). `config/sdlc_phase_config.json` is the canonical source; the DB is a seeded projection of it, never hand-edited out of sync.
- **Database access — two paths, deliberately:** Alembic + SQLAlchemy for schema migrations and one-off seed scripts only (rare operations, needs a direct connection to Supabase). The *running app* talks to Supabase's REST API instead (`app/db/rest_client.py`, plain HTTPS) for every request — a direct Postgres connection is a raw TCP connection to port 5432/6543, which some corporate networks block outright (confirmed on this project); the REST API is ordinary HTTPS, which those same networks don't block. See `backend/README.md`'s "Two ways to reach Supabase" section.
- **Storage:** abstracted behind a `StorageBackend` interface from day one. `LocalFilesystemStorage` for the POC; a `SharePointStorage`/Azure Blob implementation can be dropped in later with zero changes to agent/gating logic.

## Stack

- Backend: Python + FastAPI
- LLM: OpenAI API (GPT-4o), tool-calling for intent parsing
- DB: PostgreSQL (Supabase) — SQLAlchemy + Alembic for schema/seeding, REST API (httpx) for runtime queries
- Frontend: React + Vite (minimal chat UI, polish deferred)
- Tests: pytest

## Structure

```
/config
  sdlc_phase_config.json          # canonical source of truth

/backend
  /app
    /core
      phase_config.py             # loads & validates config json
      gating.py                   # hard-block gating logic (pure functions)
      file_naming.py              # Marlabs_<DocType>_<ClientName>_<Timestamp>
    /storage
      base.py                     # StorageBackend interface
      local.py                    # LocalFilesystemStorage
    /db
      models.py                   # Client, Phase, RequiredDocument, ClientDocument, Template (schema only)
      session.py                  # SQLAlchemy engine — migrations/seed scripts only, not runtime
      rest_client.py               # SupabaseRestClient — what the running app actually uses
      seed.py                     # seeds phases/required_docs from config json
      seed_templates.py           # seeds mock template library
      migrations/                 # alembic
    /agent
      tools.py                    # tool defs: request_template, upload_document, check_status
      orchestrator.py             # conversation loop (OpenAI)
    /api
      routes_chat.py
      routes_documents.py          # template download + document upload
    deps.py                        # FastAPI dependency providers (REST client, storage, config)
    main.py                       # FastAPI app
  /tests
    test_gating.py
    test_file_naming.py
    test_storage_local.py
    test_rest_client.py
    test_document_service.py
    test_agent_tools.py
    test_orchestrator.py

/frontend
  /src
    App.jsx                      # page shell, backend health indicator
    api.js                       # fetch wrapper for backend API
    /components
      ChatPanel.jsx               # conversational UI, POST /api/chat
      ToolActivity.jsx            # inline rendering of agent tool-call results
      UploadPanel.jsx             # completed-document upload form

/templates                        # master template store (local POC)
/clients                          # per-client phase folders (local POC, gitignored)
/docs                             # discovery docs, this design doc
```
