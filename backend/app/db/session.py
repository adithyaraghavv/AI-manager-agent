"""SQLAlchemy session factory — used only by Alembic migrations and the
one-off seed scripts (app/db/seed.py, app/db/seed_templates.py). The running
app's request path does not use this; see app/db/rest_client.py and
README.md's "Two ways to reach Supabase" section for why."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
