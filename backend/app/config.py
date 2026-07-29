from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = ""
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/delivery_agent"
    template_store_path: Path = Path("../templates")
    client_store_path: Path = Path("../clients")
    phase_config_path: Path = Path("../config/sdlc_phase_config.json")


settings = Settings()
