from functools import lru_cache

from app.config import settings
from app.core.phase_config import PhaseConfig, get_phase_config
from app.db.rest_client import SupabaseRestClient
from app.storage.base import StorageBackend
from app.storage.local import LocalFilesystemStorage


@lru_cache(maxsize=1)
def get_rest_client() -> SupabaseRestClient:
    return SupabaseRestClient(settings.supabase_url, settings.supabase_key)


@lru_cache(maxsize=1)
def get_template_storage() -> StorageBackend:
    return LocalFilesystemStorage(settings.template_store_path)


@lru_cache(maxsize=1)
def get_client_storage() -> StorageBackend:
    return LocalFilesystemStorage(settings.client_store_path)


def get_config() -> PhaseConfig:
    return get_phase_config()
