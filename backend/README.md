# Delivery AI Agent — Backend

Greenfield build. See `/docs/tech_stack_and_structure.md` for the design rationale.

## Setup

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in GROQ_API_KEY, DATABASE_URL, SUPABASE_URL, SUPABASE_KEY

# schema setup + seeding: needs DATABASE_URL, a direct-ish connection to
# Supabase. If your network blocks direct Postgres ports (some corporate
# networks do — see "Two ways to reach Supabase" below), run these three
# from a network that doesn't, e.g. a phone hotspot. This is a one-off step.
alembic upgrade head
python -m app.db.seed
python -m app.db.seed_templates   # mock template library, see docs/mock_template_library.md

# run — this only needs SUPABASE_URL/SUPABASE_KEY, works on any network
# including ones that block direct database ports
uvicorn app.main:app --reload --port 8000
```

Day-to-day, prefer running `npm run dev` from `/frontend` instead — it starts this backend and the
frontend together in one terminal (see `/frontend/README.md`). Run the command above directly only
when you want the backend on its own (e.g. `npm run dev:backend` from `/frontend` does the same
thing).

## Tests

```bash
python -m pytest tests/ -q
```

## Two ways to reach Supabase, and why both exist

This project talks to Supabase two different ways, deliberately:

1. **Direct Postgres connection** (`DATABASE_URL`, via SQLAlchemy) — used only by Alembic
   migrations and the two seed scripts (`app/db/seed.py`, `app/db/seed_templates.py`). Rare,
   occasional operations.
2. **Supabase's REST API** (`SUPABASE_URL` + `SUPABASE_KEY`, via `app/db/rest_client.py`, plain
   HTTPS) — used by everything the running app does at request time: every chat message,
   template request, and document upload goes through `app/services/*.py`, which talks to the
   REST client, never SQLAlchemy.

Why the split: a direct Postgres connection is a raw TCP connection to port 5432 or 6543, which
some corporate network firewalls block outright — confirmed on this project, not hypothetical.
The REST API is plain HTTPS (port 443), which those same firewalls essentially never block. Since
the *running app* needs to work reliably on whatever network a PM happens to be on, it uses the
REST path. Schema changes and seeding are rare enough that requiring an occasional hotspot/
different-network session for those specifically is an acceptable tradeoff, in exchange for the
app itself never being network-blocked during actual use.

If you hit `OperationalError: ... failed to resolve host` or a connection that just hangs forever
on `alembic upgrade head` or a seed script, that's this exact issue — switch networks for that one
command, it doesn't affect the running app.

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
- DB driver for the migration/seed path is `psycopg` (v3, not `psycopg2`) so `DATABASE_URL`'s
  scheme is `postgresql+psycopg://...`. Picked because `psycopg[binary]` ships prebuilt wheels
  for newer Python releases (e.g. 3.14) well before `psycopg2-binary` does — if you hit a build
  error mentioning `psycopg2`, you're on the wrong package/URL scheme.
- `SUPABASE_KEY` must be the **service_role** key (Project Settings → API), not the anon/public
  key — service_role bypasses Row Level Security, which is correct here since this backend is the
  only trusted access point (the frontend never talks to Supabase directly). Never send this key
  to a browser/frontend.
- `GET /api/clients/status` (`app/services/dashboard_service.py`) powers the manager dashboard —
  aggregates every client's phase progress and flags anyone stuck mid-phase with no activity in
  `stale_after_days` (`.env`, default 3). No gating logic here, read-only aggregation.
- `python -m app.db.seed_demo_dashboard` seeds/refreshes one realistic-looking stale demo client
  ("Globex Industries", stuck on Requirement Analysis) for demoing the stale-flag + copy-reminder
  dashboard feature without waiting days for a real client to go stale. Doesn't touch any real
  client data. Safe to re-run right before a demo — resets the timestamps back to "N days ago"
  from now (`--days-stale`, default 5).
