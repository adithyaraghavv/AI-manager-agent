from functools import lru_cache

from app.config import settings
from app.core.phase_config import PhaseConfig, get_phase_config
from app.db.rest_client import SupabaseRestClient
from app.storage.base import StorageBackend
from app.storage.local import LocalFilesystemStorage


# Required env vars per storage backend. Kept here (not inside the SharePoint
# module) so `deps.py` can surface a clear startup error listing *by name*
# any variable a deploy forgot to set — the operator shouldn't have to
# reverse-engineer which envs the backend reads.
_SHAREPOINT_REQUIRED = (
    ("SHAREPOINT_TENANT_ID", "sharepoint_tenant_id"),
    ("SHAREPOINT_CLIENT_ID", "sharepoint_client_id"),
    ("SHAREPOINT_CLIENT_SECRET", "sharepoint_client_secret"),
    ("SHAREPOINT_SITE_ID", "sharepoint_site_id"),
)


@lru_cache(maxsize=1)
def get_rest_client() -> SupabaseRestClient:
    return SupabaseRestClient(settings.supabase_url, settings.supabase_key)


def _build_sharepoint_storage(root_subpath: str) -> StorageBackend:
    """Construct a SharepointStorageBackend or raise a clear startup error.

    ``root_subpath`` is joined onto ``SHAREPOINT_ROOT_PATH`` so templates
    and per-client files land in different subfolders inside the same drive,
    mirroring how the local backend splits them into different directories.
    """
    missing = [env_name for env_name, attr in _SHAREPOINT_REQUIRED if not getattr(settings, attr)]
    if missing:
        raise RuntimeError(
            "STORAGE_BACKEND=sharepoint but required env vars are missing: "
            + ", ".join(missing)
        )
    # Lazy import so 'msal' isn't required when running with local storage.
    from app.storage.sharepoint import SharepointStorageBackend

    prefix_parts = [p for p in (settings.sharepoint_root_path.strip("/"), root_subpath) if p]
    combined_root = "/".join(prefix_parts)

    return SharepointStorageBackend(
        tenant_id=settings.sharepoint_tenant_id,
        client_id=settings.sharepoint_client_id,
        client_secret=settings.sharepoint_client_secret,
        site_id=settings.sharepoint_site_id,
        drive_id=settings.sharepoint_drive_id or None,
        root_path=combined_root,
    )


def _build_storage(local_path, sharepoint_subpath: str) -> StorageBackend:
    backend = (settings.storage_backend or "local").strip().lower()
    if backend == "local":
        return LocalFilesystemStorage(local_path)
    if backend == "sharepoint":
        return _build_sharepoint_storage(sharepoint_subpath)
    raise RuntimeError(
        f"Unknown STORAGE_BACKEND={settings.storage_backend!r}; expected 'local' or 'sharepoint'"
    )


@lru_cache(maxsize=1)
def get_template_storage() -> StorageBackend:
    return _build_storage(settings.template_store_path, "templates")


@lru_cache(maxsize=1)
def get_client_storage() -> StorageBackend:
    return _build_storage(settings.client_store_path, "clients")


def get_config() -> PhaseConfig:
    return get_phase_config()
