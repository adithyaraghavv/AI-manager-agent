# Tech Stack & Project Structure — Delivery AI Agent (Greenfield Build)

## Decisions

- **Retrieval:** structured lookup, not RAG. Claude is used only for conversational intent parsing (tool-calling), resolved against DB queries seeded from `sdlc_phase_config.json`.
- **Database:** PostgreSQL via SQLAlchemy + Alembic. `config/sdlc_phase_config.json` is the canonical source; the DB is a seeded projection of it, never hand-edited out of sync.
- **Storage:** abstracted behind a `StorageBackend` interface from day one. `LocalFilesystemStorage` for the POC; a `SharePointStorage`/Azure Blob implementation can be dropped in later with zero changes to agent/gating logic.

## Stack

- Backend: Python + FastAPI
- LLM: Claude via Anthropic API, tool-calling for intent parsing
- DB: PostgreSQL + SQLAlchemy + Alembic
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
      models.py                   # Client, Phase, RequiredDocument, ClientDocument, Template
      seed.py                     # seeds phases/required_docs from config json
      migrations/                 # alembic
    /agent
      tools.py                    # Claude tool defs: request_template, upload_document, check_status
      orchestrator.py             # conversation loop
    /api
      routes_chat.py
      routes_templates.py
      routes_upload.py
    main.py                       # FastAPI app
  /tests
    test_gating.py
    test_file_naming.py
    test_storage_local.py

/frontend
  /src                            # React chat UI

/templates                        # master template store (local POC)
/clients                          # per-client phase folders (local POC, gitignored)
/docs                             # discovery docs, this design doc
```
