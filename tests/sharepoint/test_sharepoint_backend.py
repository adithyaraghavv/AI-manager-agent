"""Contract tests for SharepointStorageBackend.

Every assertion the LocalFilesystemStorage contract test makes
(backend/tests/test_storage_local.py) has a mirror here, executed
against a fake Graph API implemented in-process. Point: the swap
from local -> SharePoint must be transparent to the rest of the app,
so both backends have to satisfy the same behavioural contract.

Uses `respx` if installed, else falls back to a lightweight
in-memory fake httpx.Client — the fake is what actually powers the
assertions below, since respx would require the real Graph host
schema. Either way, no real network calls are made.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Optional
from unittest.mock import MagicMock

import httpx
import pytest

from app.storage.sharepoint import SharepointStorageBackend


# ---------------------------------------------------------------------------
# In-memory fake of the subset of Microsoft Graph the backend uses.
# Deliberately small: enough to exercise round-trips + error paths, not a
# full simulator. Mirrors the /sites/{id}/drive/root:/<path>:/content shape.
# ---------------------------------------------------------------------------
class _FakeGraph:
    def __init__(self):
        # path (str) -> bytes for files, or None for folders
        self._items: dict[str, Optional[bytes]] = {"": None}  # root always exists
        self.calls: list[tuple[str, str]] = []  # (method, url) for assertions

    # ---- helpers ----------------------------------------------------------
    def _parse_path(self, url: str) -> str:
        """Extract the path from a Graph URL. Handles ``root:/foo/bar:`` and
        ``root:/foo/bar:/content`` and ``root/children`` variants."""
        # Strip query string
        url = url.split("?", 1)[0]
        # Trim the /content or /children suffix if present
        for suffix in ("/content", "/children"):
            if url.endswith(suffix):
                url = url[: -len(suffix)]
        # Root drive item
        if url.endswith("/root") or url.endswith("/drive"):
            return ""
        # ``.../root:/<encoded-path>:``  or  ``.../root:/<encoded-path>``
        marker = "/root:/"
        idx = url.find(marker)
        if idx == -1:
            return ""
        path = url[idx + len(marker) :]
        if path.endswith(":"):
            path = path[:-1]
        # URL-decode
        import urllib.parse
        return urllib.parse.unquote(path)

    def _is_folder(self, path: str) -> bool:
        return path in self._items and self._items[path] is None

    def _exists(self, path: str) -> bool:
        return path in self._items

    # ---- httpx.Client stand-in --------------------------------------------
    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        self.calls.append((method, url))
        path = self._parse_path(url)

        if method == "GET":
            if url.endswith("/content"):
                if not self._exists(path) or self._is_folder(path):
                    return httpx.Response(404, text="not found")
                return httpx.Response(200, content=self._items[path])
            if url.endswith("/children"):
                if not self._is_folder(path):
                    return httpx.Response(404, text="not found")
                # Return direct children only (non-recursive)
                prefix = f"{path}/" if path else ""
                children = []
                for p, val in self._items.items():
                    if p == path or not p.startswith(prefix):
                        continue
                    rest = p[len(prefix) :]
                    if "/" in rest:
                        continue
                    children.append({"name": rest, "folder": {} if val is None else None})
                return httpx.Response(200, json={"value": children})
            # Bare item metadata
            if self._exists(path):
                return httpx.Response(200, json={"name": path.split("/")[-1] or "root"})
            return httpx.Response(404, text="not found")

        if method == "PUT":
            if url.endswith("/content"):
                # Simple upload creates the file (and any parent folders).
                parts = path.split("/") if path else []
                for i in range(len(parts) - 1):
                    intermediate = "/".join(parts[: i + 1])
                    self._items.setdefault(intermediate, None)
                self._items[path] = kwargs.get("content", b"")
                return httpx.Response(201, json={"name": parts[-1] if parts else ""})
            return httpx.Response(400, text="unsupported")

        if method == "POST":
            # Folder create: POST .../children with {name, folder}
            body = kwargs.get("json") or {}
            name = body.get("name")
            if not name:
                return httpx.Response(400, text="bad request")
            parent = path
            new_path = f"{parent}/{name}" if parent else name
            self._items[new_path] = None
            return httpx.Response(201, json={"name": name, "folder": {}})

        if method == "DELETE":
            if not self._exists(path):
                return httpx.Response(404, text="not found")
            # Recursive delete for folders
            to_remove = [p for p in list(self._items) if p == path or p.startswith(f"{path}/")]
            for p in to_remove:
                del self._items[p]
            return httpx.Response(204)

        return httpx.Response(405, text="method not allowed")

    def get(self, url, **kw): return self.request("GET", url, **kw)
    def put(self, url, **kw): return self.request("PUT", url, **kw)
    def post(self, url, **kw): return self.request("POST", url, **kw)
    def delete(self, url, **kw): return self.request("DELETE", url, **kw)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def fake_graph():
    return _FakeGraph()


@pytest.fixture
def fake_msal():
    """Stand-in for msal.ConfidentialClientApplication.

    Returns a token that's valid for an hour; the token-caching tests in
    test_auth_msal.py drive the timing separately.
    """
    app = MagicMock()
    app.acquire_token_for_client.return_value = {
        "access_token": "test-token",
        "expires_in": 3600,
    }
    return app


@pytest.fixture
def storage(fake_graph, fake_msal):
    return SharepointStorageBackend(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        site_id="contoso.sharepoint.com,site-guid,web-guid",
        drive_id="drive-guid",
        root_path="",
        http_client=fake_graph,  # duck-typed as an httpx.Client
        msal_app=fake_msal,
    )


# ---------------------------------------------------------------------------
# Contract tests — mirror backend/tests/test_storage_local.py
# ---------------------------------------------------------------------------
def test_save_and_get_roundtrip(storage):
    storage.save("Client1/01_Pre-requisites/file.txt", b"hello")
    assert storage.get("Client1/01_Pre-requisites/file.txt") == b"hello"


def test_exists(storage):
    assert not storage.exists("nope.txt")
    storage.save("nope.txt", b"x")
    assert storage.exists("nope.txt")


def test_get_missing_raises(storage):
    with pytest.raises(FileNotFoundError):
        storage.get("missing.txt")


def test_make_dir_and_list(storage):
    storage.make_dir("Client1/01_Pre-requisites")
    storage.make_dir("Client1/02_Requirement Analysis")
    entries = storage.list("Client1")
    assert len(entries) == 2


def test_path_escape_blocked(storage):
    with pytest.raises(ValueError):
        storage.save("../escape.txt", b"x")


def test_path_escape_blocked_nested(storage):
    with pytest.raises(ValueError):
        storage.get("Client1/../../etc/passwd")


def test_delete_dir_removes_everything_under_it(storage):
    storage.save("Client1/01_Pre-requisites/file.txt", b"hello")
    storage.save("Client1/02_Requirement Analysis/other.txt", b"world")

    storage.delete_dir("Client1")

    assert not storage.exists("Client1")


def test_delete_dir_missing_is_a_noop(storage):
    storage.delete_dir("NeverExisted")  # should not raise


def test_delete_dir_refuses_to_wipe_storage_root(storage):
    storage.save("Client1/file.txt", b"x")
    with pytest.raises(ValueError):
        storage.delete_dir("")
    # Confirm nothing was actually touched
    assert storage.exists("Client1/file.txt")


def test_delete_dir_refuses_dot(storage):
    with pytest.raises(ValueError):
        storage.delete_dir(".")


def test_delete_file_missing_is_noop(storage):
    # Should not raise — matches LocalFilesystemStorage.delete contract.
    storage.delete("nothing/here.txt")


def test_list_missing_prefix_returns_empty(storage):
    assert storage.list("nope") == []


# ---------------------------------------------------------------------------
# SharePoint-specific behaviour
# ---------------------------------------------------------------------------
def test_urls_include_site_and_drive_ids(fake_graph, fake_msal):
    storage = SharepointStorageBackend(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        site_id="contoso.sharepoint.com,site-guid,web-guid",
        drive_id="drive-guid",
        http_client=fake_graph,
        msal_app=fake_msal,
    )
    storage.save("dir/file.txt", b"x")
    # Some call must target the configured site + drive.
    assert any(
        "sites/contoso.sharepoint.com,site-guid,web-guid" in url
        and "drives/drive-guid" in url
        for _, url in fake_graph.calls
    )


def test_falls_back_to_default_drive_when_drive_id_absent(fake_graph, fake_msal):
    storage = SharepointStorageBackend(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        site_id="site-id",
        drive_id=None,
        http_client=fake_graph,
        msal_app=fake_msal,
    )
    storage.save("file.txt", b"x")
    assert any("/sites/site-id/drive/" in url for _, url in fake_graph.calls)


def test_root_path_prefix_is_applied(fake_graph, fake_msal):
    storage = SharepointStorageBackend(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        site_id="site-id",
        drive_id="drive-guid",
        root_path="DeliveryAgent/clients",
        http_client=fake_graph,
        msal_app=fake_msal,
    )
    storage.save("Client1/file.txt", b"x")
    # Callers pass "Client1/file.txt" but Graph must see the prefixed path.
    assert any("DeliveryAgent/clients/Client1/file.txt" in url for _, url in fake_graph.calls)


def test_authorization_header_sent(fake_graph, fake_msal):
    """Every call must carry the bearer token from MSAL."""
    # Patch fake_graph.request to capture headers this time.
    seen_headers: list[dict] = []
    original = fake_graph.request

    def capture(method, url, **kwargs):
        seen_headers.append(kwargs.get("headers") or {})
        return original(method, url, **kwargs)

    fake_graph.request = capture  # type: ignore[assignment]

    storage = SharepointStorageBackend(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        site_id="site-id",
        drive_id="drive-guid",
        http_client=fake_graph,
        msal_app=fake_msal,
    )
    storage.save("file.txt", b"x")
    assert seen_headers, "expected at least one HTTP call"
    assert all(h.get("Authorization") == "Bearer test-token" for h in seen_headers)


def test_special_characters_in_path_are_url_encoded(fake_graph, fake_msal):
    storage = SharepointStorageBackend(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        site_id="site-id",
        drive_id="drive-guid",
        http_client=fake_graph,
        msal_app=fake_msal,
    )
    storage.save("Client1/02_Requirement Analysis/spec.txt", b"content")
    # Space must be encoded as %20 on the wire.
    assert any("%20" in url for _, url in fake_graph.calls)


def test_missing_required_config_raises_at_construction(fake_graph, fake_msal):
    """Config problems must surface at startup, not later at first request."""
    with pytest.raises(ValueError, match="client_secret"):
        SharepointStorageBackend(
            tenant_id="tenant",
            client_id="client",
            client_secret="",
            site_id="site-id",
            http_client=fake_graph,
            msal_app=fake_msal,
        )
