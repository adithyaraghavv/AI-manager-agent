"""DI-factory tests: STORAGE_BACKEND must pick the right implementation
and must fail *loudly* when SharePoint is selected without full config.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from unittest.mock import patch

import pytest


def _reload_deps_with_settings(monkeypatch, **overrides):
    """Re-import app.config + app.deps with the given env overrides.

    ``get_client_storage`` / ``get_template_storage`` use ``lru_cache``,
    so we reload the module to make sure each test starts from a clean
    cache and a fresh Settings() built from the current env.
    """
    # Wipe env vars we care about so the parent shell doesn't leak in.
    for key in (
        "STORAGE_BACKEND",
        "SHAREPOINT_TENANT_ID",
        "SHAREPOINT_CLIENT_ID",
        "SHAREPOINT_CLIENT_SECRET",
        "SHAREPOINT_SITE_ID",
        "SHAREPOINT_DRIVE_ID",
        "SHAREPOINT_ROOT_PATH",
        "TEMPLATE_STORE_PATH",
        "CLIENT_STORE_PATH",
    ):
        monkeypatch.delenv(key, raising=False)
    for k, v in overrides.items():
        monkeypatch.setenv(k, v)

    # Reload the modules so the new env is picked up.
    import app.config
    import app.deps
    importlib.reload(app.config)
    importlib.reload(app.deps)
    return app.deps


def test_defaults_to_local_backend(monkeypatch, tmp_path):
    deps = _reload_deps_with_settings(
        monkeypatch,
        TEMPLATE_STORE_PATH=str(tmp_path / "templates"),
        CLIENT_STORE_PATH=str(tmp_path / "clients"),
    )
    from app.storage.local import LocalFilesystemStorage

    assert isinstance(deps.get_client_storage(), LocalFilesystemStorage)
    assert isinstance(deps.get_template_storage(), LocalFilesystemStorage)


def test_explicit_local_backend(monkeypatch, tmp_path):
    deps = _reload_deps_with_settings(
        monkeypatch,
        STORAGE_BACKEND="local",
        TEMPLATE_STORE_PATH=str(tmp_path / "templates"),
        CLIENT_STORE_PATH=str(tmp_path / "clients"),
    )
    from app.storage.local import LocalFilesystemStorage

    assert isinstance(deps.get_client_storage(), LocalFilesystemStorage)


def test_sharepoint_backend_when_fully_configured(monkeypatch):
    deps = _reload_deps_with_settings(
        monkeypatch,
        STORAGE_BACKEND="sharepoint",
        SHAREPOINT_TENANT_ID="tenant",
        SHAREPOINT_CLIENT_ID="client",
        SHAREPOINT_CLIENT_SECRET="secret",
        SHAREPOINT_SITE_ID="site-id",
    )
    from app.storage.sharepoint import SharepointStorageBackend

    # Mock MSAL app so no real HTTP client is initialised — factory
    # shouldn't try to reach AAD just to *construct* the backend.
    with patch("app.storage.sharepoint.SharepointStorageBackend.__init__", return_value=None) as init:
        deps.get_client_storage()
    init.assert_called_once()
    kwargs = init.call_args.kwargs
    assert kwargs["tenant_id"] == "tenant"
    assert kwargs["client_id"] == "client"
    assert kwargs["client_secret"] == "secret"
    assert kwargs["site_id"] == "site-id"


@pytest.mark.parametrize(
    "missing_env",
    [
        "SHAREPOINT_TENANT_ID",
        "SHAREPOINT_CLIENT_ID",
        "SHAREPOINT_CLIENT_SECRET",
        "SHAREPOINT_SITE_ID",
    ],
)
def test_sharepoint_with_missing_env_fails_startup(monkeypatch, missing_env):
    env = {
        "STORAGE_BACKEND": "sharepoint",
        "SHAREPOINT_TENANT_ID": "tenant",
        "SHAREPOINT_CLIENT_ID": "client",
        "SHAREPOINT_CLIENT_SECRET": "secret",
        "SHAREPOINT_SITE_ID": "site-id",
    }
    env.pop(missing_env)
    deps = _reload_deps_with_settings(monkeypatch, **env)

    with pytest.raises(RuntimeError, match=missing_env):
        deps.get_client_storage()


def test_unknown_storage_backend_value_is_a_startup_error(monkeypatch, tmp_path):
    deps = _reload_deps_with_settings(
        monkeypatch,
        STORAGE_BACKEND="s3",  # not supported
        TEMPLATE_STORE_PATH=str(tmp_path / "templates"),
        CLIENT_STORE_PATH=str(tmp_path / "clients"),
    )
    with pytest.raises(RuntimeError, match="Unknown STORAGE_BACKEND"):
        deps.get_client_storage()
