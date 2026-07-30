# Delivery AI Agent — Backend

Greenfield build. See `/docs/tech_stack_and_structure.md` for the design rationale.

## Setup

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in GROQ_API_KEY and DATABASE_URL

# create the Postgres database (adjust to your local setup)
createdb delivery_agent

# apply schema
alembic upgrade head

# seed phases/required documents from config/sdlc_phase_config.json
python -m app.db.seed

# seed a mock template library (placeholder files) until real SharePoint
# templates are available — see docs/mock_template_library.md
python -m app.db.seed_templates

# run
uvicorn app.main:app --reload --port 8000
```

## Tests

```bash
python -m pytest tests/ -q
```

## Notes

- `config/sdlc_phase_config.json` is the single source of truth for phases and required
  documents — the DB is a seeded projection of it (`app/db/seed.py`), never edited by hand.
- Storage is abstracted behind `app/storage/base.py::StorageBackend`. `LocalFilesystemStorage`
  is used for the POC; a SharePoint/Azure Blob implementation can be swapped in later with no
  changes to gating or service logic.
- Master templates: until real SharePoint access is available, `app/db/seed_templates.py`
  seeds a mock template library (placeholder files + DB rows) so the full request/gate/
  download/upload flow can be tested end-to-end. See `docs/mock_template_library.md` for
  the structure and exactly what changes when real templates are available (no code changes,
  only a new `StorageBackend` implementation + re-pointing config).
- Phase-gating is enforced as a hard block in `app/services/document_service.py`, independent
  of the conversational agent — the agent can only ask for the same checks the REST API enforces.
- DB driver is `psycopg` (v3, not `psycopg2`) so the `DATABASE_URL` scheme is
  `postgresql+psycopg://...`. This was picked specifically because `psycopg[binary]` ships
  prebuilt wheels for newer Python releases (e.g. 3.14) well before `psycopg2-binary` does —
  if you hit a build error mentioning `psycopg2`, you're on the wrong package/URL scheme.
