"""SharePoint / Microsoft Graph implementation of StorageBackend.

Files/folders live inside a single SharePoint site's document library
(drive). Auth is app-only (client credentials) via MSAL; every Graph
call carries a short-lived bearer token that we cache and refresh
in-process. See ``docs/features/sharepoint-storage.md`` for the
Azure AD / IT-side setup this implementation assumes.
"""
from __future__ import annotations

import time
import urllib.parse
from typing import Optional

import httpx

from app.storage.base import StorageBackend


GRAPH_BASE = "https://graph.microsoft.com/v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"
# Refresh the token this many seconds *before* it actually expires so an
# in-flight request never gets a 401 due to a token that expired between
# "acquire" and "use".
TOKEN_REFRESH_MARGIN_SECONDS = 300


class SharepointStorageBackend(StorageBackend):
    """Store files in a SharePoint document library via Microsoft Graph.

    Path handling matches ``LocalFilesystemStorage``:

    - Paths are forward-slash separated, relative, and MUST NOT contain
      ``..`` segments (would otherwise let a caller escape the configured
      root folder — same threat as on the local backend).
    - The configured ``root_path`` (optional) is joined to every path
      before it hits Graph, so callers pass the same
      ``"Client1/01_Pre-requisites/file.txt"`` shape as before.
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        site_id: str,
        drive_id: Optional[str] = None,
        root_path: str = "",
        *,
        http_client: Optional[httpx.Client] = None,
        msal_app=None,
    ):
        # Fail *at construction* if the caller forgot a secret — the point is
        # for a bad config to surface at startup, not on the first upload
        # some hours later.
        missing = [
            name
            for name, value in (
                ("tenant_id", tenant_id),
                ("client_id", client_id),
                ("client_secret", client_secret),
                ("site_id", site_id),
            )
            if not value
        ]
        if missing:
            raise ValueError(
                f"SharepointStorageBackend missing required config: {', '.join(missing)}"
            )

        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.site_id = site_id
        self.drive_id = drive_id
        # Normalize root_path (strip leading/trailing slashes) so it composes
        # cleanly with per-call paths.
        self.root_path = root_path.strip("/") if root_path else ""

        self._http = http_client or httpx.Client(timeout=30.0)
        self._msal_app = msal_app  # injectable for tests
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._resolved_drive_id: Optional[str] = drive_id

    # ------------------------------------------------------------------
    # Path handling — same rules as LocalFilesystemStorage
    # ------------------------------------------------------------------
    def _normalize(self, path: str) -> str:
        """Validate + normalize a caller-supplied path.

        Returns the path as it should appear *relative to the drive root*
        (i.e. with ``root_path`` prepended, if configured).
        """
        if path is None:
            raise ValueError("Path must not be None")
        # Reject absolute paths and traversal — matches the local backend's
        # "the resolved path must stay under root" rule, checked structurally
        # here since we're not on a real filesystem.
        clean = path.replace("\\", "/").strip("/")
        parts = [p for p in clean.split("/") if p not in ("", ".")]
        for p in parts:
            if p == "..":
                raise ValueError(f"Path {path!r} escapes storage root")
        rel = "/".join(parts)
        if self.root_path:
            return f"{self.root_path}/{rel}" if rel else self.root_path
        return rel

    def _encode(self, path: str) -> str:
        """Percent-encode a Graph path, preserving forward slashes."""
        # Graph's ``/root:/<path>:`` syntax requires per-segment URL encoding.
        return "/".join(urllib.parse.quote(seg, safe="") for seg in path.split("/"))

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def _get_msal_app(self):
        if self._msal_app is not None:
            return self._msal_app
        # Import lazily so tests that mock auth don't need msal installed.
        import msal  # noqa: WPS433 — lazy import is deliberate

        self._msal_app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            client_credential=self.client_secret,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
        )
        return self._msal_app

    def _acquire_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at - TOKEN_REFRESH_MARGIN_SECONDS:
            return self._token
        app = self._get_msal_app()
        result = app.acquire_token_for_client(scopes=[GRAPH_SCOPE])
        if not isinstance(result, dict) or "access_token" not in result:
            err = result.get("error_description") if isinstance(result, dict) else str(result)
            raise RuntimeError(f"MSAL failed to acquire token: {err}")
        self._token = result["access_token"]
        # ``expires_in`` is seconds-from-now per MSAL's contract.
        self._token_expires_at = now + int(result.get("expires_in", 3600))
        return self._token

    def _headers(self, extra: Optional[dict] = None) -> dict:
        headers = {"Authorization": f"Bearer {self._acquire_token()}"}
        if extra:
            headers.update(extra)
        return headers

    # ------------------------------------------------------------------
    # Graph URL helpers
    # ------------------------------------------------------------------
    def _drive_root(self) -> str:
        """Return the Graph URL prefix for the drive root (no trailing slash)."""
        if self._resolved_drive_id:
            return f"{GRAPH_BASE}/sites/{self.site_id}/drives/{self._resolved_drive_id}"
        # Fall back to the site's default document library.
        return f"{GRAPH_BASE}/sites/{self.site_id}/drive"

    def _item_url(self, path: str) -> str:
        """Graph URL for a drive item at ``path`` (relative to drive root)."""
        normalized = self._normalize(path)
        if not normalized:
            # The drive root itself.
            return f"{self._drive_root()}/root"
        return f"{self._drive_root()}/root:/{self._encode(normalized)}:"

    # ------------------------------------------------------------------
    # StorageBackend interface
    # ------------------------------------------------------------------
    def save(self, path: str, content: bytes) -> None:
        # Ensure parent folder exists — Graph's PUT-content endpoint creates
        # missing intermediate folders for us as long as the drive item path
        # includes them, but only reliably for the simple-upload path we use.
        normalized = self._normalize(path)
        if not normalized:
            raise ValueError("Cannot save to storage root itself")
        url = f"{self._drive_root()}/root:/{self._encode(normalized)}:/content"
        resp = self._http.put(
            url,
            headers=self._headers({"Content-Type": "application/octet-stream"}),
            content=content,
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Graph PUT {url} failed: {resp.status_code} {resp.text}"
            )

    def get(self, path: str) -> bytes:
        url = f"{self._item_url(path)}/content"
        resp = self._http.get(url, headers=self._headers(), follow_redirects=True)
        if resp.status_code == 404:
            raise FileNotFoundError(path)
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Graph GET {url} failed: {resp.status_code} {resp.text}"
            )
        return resp.content

    def exists(self, path: str) -> bool:
        url = self._item_url(path)
        resp = self._http.get(url, headers=self._headers())
        if resp.status_code == 404:
            return False
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Graph GET {url} failed: {resp.status_code} {resp.text}"
            )
        return True

    def list(self, prefix: str) -> list[str]:
        url = f"{self._item_url(prefix)}/children"
        resp = self._http.get(url, headers=self._headers())
        if resp.status_code == 404:
            return []
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Graph GET {url} failed: {resp.status_code} {resp.text}"
            )
        # Return paths in the same "relative to storage root" shape the
        # local backend returns — strip the configured root_path prefix if any.
        base = self._normalize(prefix)
        entries = []
        for item in resp.json().get("value", []):
            name = item.get("name")
            if not name:
                continue
            full = f"{base}/{name}" if base else name
            if self.root_path and full.startswith(self.root_path + "/"):
                full = full[len(self.root_path) + 1 :]
            elif self.root_path and full == self.root_path:
                full = ""
            entries.append(full)
        return sorted(entries)

    def delete(self, path: str) -> None:
        url = self._item_url(path)
        resp = self._http.delete(url, headers=self._headers())
        if resp.status_code == 404:
            return  # no-op, matches LocalFilesystemStorage.delete contract
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Graph DELETE {url} failed: {resp.status_code} {resp.text}"
            )

    def make_dir(self, path: str) -> None:
        normalized = self._normalize(path)
        if not normalized:
            return  # drive root always exists
        # Create the folder (and its parents) by walking segments — Graph's
        # /children create-folder endpoint only creates one level at a time.
        parts = normalized.split("/")
        parent = ""
        for i, segment in enumerate(parts):
            parent_full = "/".join(parts[:i])
            child_full = "/".join(parts[: i + 1])
            if parent_full:
                parent_url = f"{self._drive_root()}/root:/{self._encode(parent_full)}:/children"
            else:
                parent_url = f"{self._drive_root()}/root/children"
            # If the folder already exists, skip; otherwise create it.
            check_url = f"{self._drive_root()}/root:/{self._encode(child_full)}:"
            check = self._http.get(check_url, headers=self._headers())
            if check.status_code == 200:
                parent = child_full
                continue
            if check.status_code != 404 and check.status_code >= 400:
                raise RuntimeError(
                    f"Graph GET {check_url} failed: {check.status_code} {check.text}"
                )
            body = {
                "name": segment,
                "folder": {},
                # Rename on conflict is safer than 'fail' for concurrent creates.
                "@microsoft.graph.conflictBehavior": "replace",
            }
            resp = self._http.post(
                parent_url,
                headers=self._headers({"Content-Type": "application/json"}),
                json=body,
            )
            if resp.status_code >= 400:
                raise RuntimeError(
                    f"Graph POST {parent_url} failed: {resp.status_code} {resp.text}"
                )
            parent = child_full

    def web_url(self, path: str) -> Optional[str]:
        """Graph returns a real ``webUrl`` on every drive item — the exact
        link SharePoint's own UI would show if you navigated there by hand.
        Best-effort: any failure (network, permissions, item not found)
        returns None rather than raising, since a missing link should never
        break the caller's actual result."""
        try:
            resp = self._http.get(self._item_url(path), headers=self._headers())
        except httpx.HTTPError:
            return None
        if resp.status_code != 200:
            return None
        return resp.json().get("webUrl")

    def delete_dir(self, path: str) -> None:
        # Refuse to wipe the configured root — same guard as LocalFilesystemStorage.
        # Blank/"." would otherwise resolve to the drive root (or root_path)
        # and nuke every client's data at once.
        stripped = path.strip("/") if path else ""
        if not stripped or stripped == ".":
            raise ValueError("Refusing to delete the storage root itself")
        normalized = self._normalize(path)
        if not normalized:
            raise ValueError("Refusing to delete the storage root itself")
        url = self._item_url(path)
        resp = self._http.delete(url, headers=self._headers())
        if resp.status_code == 404:
            return
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Graph DELETE {url} failed: {resp.status_code} {resp.text}"
            )
