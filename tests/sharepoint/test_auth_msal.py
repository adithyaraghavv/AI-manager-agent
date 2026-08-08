"""MSAL token caching / refresh behaviour.

These tests exercise the token lifecycle in isolation from any Graph
call, by driving ``SharepointStorageBackend._acquire_token`` directly
against a mocked MSAL app and manipulating the internal expiry clock.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.storage.sharepoint import SharepointStorageBackend, TOKEN_REFRESH_MARGIN_SECONDS


def _make_msal(tokens):
    """Return a mock MSAL app that yields the given tokens on successive calls."""
    app = MagicMock()
    app.acquire_token_for_client.side_effect = list(tokens)
    return app


def _make_backend(msal_app):
    return SharepointStorageBackend(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        site_id="site-id",
        drive_id="drive-guid",
        http_client=MagicMock(),
        msal_app=msal_app,
    )


# ---------------------------------------------------------------------------
# Caching / refresh
# ---------------------------------------------------------------------------
def test_token_is_cached_within_ttl():
    msal_app = _make_msal([
        {"access_token": "tok-1", "expires_in": 3600},
    ])
    backend = _make_backend(msal_app)

    # Multiple acquisitions inside the TTL should hit MSAL exactly once.
    assert backend._acquire_token() == "tok-1"
    assert backend._acquire_token() == "tok-1"
    assert backend._acquire_token() == "tok-1"
    assert msal_app.acquire_token_for_client.call_count == 1


def test_fresh_token_requested_after_expiry():
    msal_app = _make_msal([
        {"access_token": "tok-1", "expires_in": 3600},
        {"access_token": "tok-2", "expires_in": 3600},
    ])
    backend = _make_backend(msal_app)

    first = backend._acquire_token()
    assert first == "tok-1"
    assert msal_app.acquire_token_for_client.call_count == 1

    # Force the cached token past its expiry.
    backend._token_expires_at = time.time() - 1

    second = backend._acquire_token()
    assert second == "tok-2"
    assert msal_app.acquire_token_for_client.call_count == 2


def test_token_refreshed_within_the_5_minute_safety_margin():
    """We must refresh BEFORE the token actually expires so an in-flight
    request never gets a 401 due to expiry between 'acquire' and 'use'."""
    msal_app = _make_msal([
        {"access_token": "tok-1", "expires_in": 3600},
        {"access_token": "tok-2", "expires_in": 3600},
    ])
    backend = _make_backend(msal_app)
    backend._acquire_token()

    # Pretend the token expires in less than the safety margin.
    backend._token_expires_at = time.time() + (TOKEN_REFRESH_MARGIN_SECONDS - 30)

    assert backend._acquire_token() == "tok-2"
    assert msal_app.acquire_token_for_client.call_count == 2


def test_msal_failure_raises_clear_error():
    msal_app = MagicMock()
    msal_app.acquire_token_for_client.return_value = {
        "error": "invalid_client",
        "error_description": "bad secret",
    }
    backend = _make_backend(msal_app)

    with pytest.raises(RuntimeError, match="bad secret"):
        backend._acquire_token()


# ---------------------------------------------------------------------------
# Fail-fast construction
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "kwargs, expected_missing",
    [
        (dict(tenant_id="", client_id="c", client_secret="s", site_id="s"), "tenant_id"),
        (dict(tenant_id="t", client_id="", client_secret="s", site_id="s"), "client_id"),
        (dict(tenant_id="t", client_id="c", client_secret="", site_id="s"), "client_secret"),
        (dict(tenant_id="t", client_id="c", client_secret="s", site_id=""), "site_id"),
    ],
)
def test_missing_config_raises_at_construction(kwargs, expected_missing):
    """Config errors must surface at construction, NOT at first use.

    The whole point of validating in __init__: a bad deploy fails the
    process on startup instead of waiting for a user to trigger the
    first upload hours later.
    """
    with pytest.raises(ValueError, match=expected_missing):
        SharepointStorageBackend(
            http_client=MagicMock(),
            msal_app=MagicMock(),
            **kwargs,
        )


def test_construction_succeeds_without_msal_when_no_real_call_made():
    """Constructing should NOT trigger an MSAL import until first token use."""
    # Simply confirm no exception is raised with a mocked msal_app.
    backend = SharepointStorageBackend(
        tenant_id="t",
        client_id="c",
        client_secret="s",
        site_id="site",
        http_client=MagicMock(),
        msal_app=MagicMock(),
    )
    assert backend._token is None  # not fetched yet
