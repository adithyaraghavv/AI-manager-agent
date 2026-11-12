# AI Manager Agent

An internal Marlabs tool that helps a delivery manager (or PM) track client projects
through a fixed 7-phase document lifecycle — Pre-requisites, Requirement Analysis,
System Design, Implementation, Testing, Deployment, Maintenance — without anyone
accidentally skipping a required document or losing track of who's stuck where.

It's two things in one app:

1. **A conversational assistant** — a PM can ask in plain English for a template,
   check a client's status, or upload a completed document.
2. **A manager dashboard** — a portfolio-level view of every client at once, with
   clients flagged automatically if they've gone quiet mid-phase.

The core rule the whole system is built around: **a document belonging to phase N
can't be requested or filed until every required document from every earlier phase
already exists for that client.** This is enforced as a hard block in the backend,
not a suggestion — the conversational agent can't talk its way around it, because
the check happens in the API layer regardless of what the AI says.

For the full feature list, what's built vs. still pending, and the complete tech
stack, see **[PROJECT_OVERVIEW.md](./PROJECT_OVERVIEW.md)**.

## Quick start

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

Every time after that, from `/frontend`:

```bash
npm run dev
```

This starts both the backend (port 8000) and frontend (port 5173) together in one
terminal. Open `http://localhost:5173`.

See [`backend/README.md`](./backend/README.md) and
[`frontend/README.md`](./frontend/README.md) for setup details specific to each
side, [`docs/WORKFLOW.md`](./docs/WORKFLOW.md) for how a document moves through
the system (with flowcharts), and [`docs/`](./docs) for the original discovery
documentation and database structure.

## Tech stack

**Backend** — Python 3.11, FastAPI, [Groq](https://groq.com/) (Llama 3.3 70B) for
the chat agent, [Supabase](https://supabase.com/) (Postgres via REST API), pytest
(67 tests).

**Frontend** — React 19 + Vite, plain JS, hand-written CSS.

**Storage** — abstracted behind `StorageBackend`
(`backend/app/storage/base.py`), currently a local filesystem mock, designed to be
swapped for a SharePoint implementation later with no changes to gating or
service logic.
