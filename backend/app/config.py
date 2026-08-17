from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Anchor default paths on the app package location so they resolve the same
# whether the app runs from `backend/`, from the repo root under pytest, or
# from a container with a different WORKDIR. Env vars override, so this only
# matters when nothing is set.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""

    # Used only for Alembic migrations and the one-off seed scripts — a rare,
    # occasional operation you can run from any network that reaches Supabase
    # directly (e.g. a hotspot), not something the running app depends on.
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/delivery_agent"

    # Used by the running app for every chat/upload/download request, via
    # Supabase's REST API (app/db/rest_client.py) — plain HTTPS, so it works
    # even on networks that block direct database ports.
    supabase_url: str = ""
    supabase_key: str = ""

    template_store_path: Path = _REPO_ROOT / "templates"
    client_store_path: Path = _REPO_ROOT / "clients"
    phase_config_path: Path = _REPO_ROOT / "config" / "sdlc_phase_config.json"

    # A client is flagged "stale" on the manager dashboard if it's been this
    # many days since any document was filed while it's still mid-phase.
    stale_after_days: int = 3


settings = Settings()
