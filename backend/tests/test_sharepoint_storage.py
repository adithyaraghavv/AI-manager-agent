"""SharepointStorageBackend.web_url — the only piece of the SharePoint
backend not already exercised indirectly through the local-storage-backed
service/tool tests (everything else in this backend mirrors
LocalFilesystemStorage's contract exactly)."""

import httpx
import pytest

from app.storage.sharepoint import SharepointStorageBackend


class FakeMsalApp:
    def acquire_token_for_client(self, scopes):
        return {"access_token": "fake-token", "expires_in": 3600}


def make_backend(handler) -> SharepointStorageBackend:
    transport = httpx.MockTransport(handler)
    return SharepointStorageBackend(
        tenant_id="t",
        client_id="c",
        client_secret="s",
        site_id="site",
        http_client=httpx.Client(transport=transport),
        msal_app=FakeMsalApp(),
    )


def test_web_url_returns_graphs_weburl_field():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"webUrl": "https://marlabs.sharepoint.com/sites/x/Clients/Acme"})

    backend = make_backend(handler)
    assert backend.web_url("Acme") == "https://marlabs.sharepoint.com/sites/x/Clients/Acme"


def test_web_url_returns_none_when_item_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "not found"}})

    backend = make_backend(handler)
    assert backend.web_url("Ghost") is None


def test_web_url_returns_none_on_network_error_rather_than_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    backend = make_backend(handler)
    assert backend.web_url("Acme") is None
