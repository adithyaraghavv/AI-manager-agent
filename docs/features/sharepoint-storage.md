# SharePoint Storage Backend

Optional storage backend that puts every file the agent reads/writes into
a SharePoint document library instead of the local filesystem. Selected
at startup via `STORAGE_BACKEND=sharepoint`; the rest of the app doesn't
change.

## Why it exists

The POC ships with `LocalFilesystemStorage` (see `backend/app/storage/local.py`),
which is fine for a laptop demo but useless the moment more than one
instance of the app runs or a PM wants the same folder tree in the same
place their team already lives (SharePoint). This backend is the drop-in
replacement.

## Architecture

```
+-----------+   settings.storage_backend    +---------------------------+
|  app/deps | ----------------------------> | SharepointStorageBackend  |
+-----------+                               +---------------------------+
                                                  |
                                                  |  MSAL client-credentials flow
                                                  v
                                            +----------------+
                                            |  AAD token EP  |  (login.microsoftonline.com)
                                            +----------------+
                                                  |  bearer token (cached ~1h)
                                                  v
                                            +----------------+
                                            |  Graph API     |  (graph.microsoft.com)
                                            +----------------+
                                                  |
                                                  v
                                        SharePoint document library
                                        (site / drive / root_path)
```

### Graph endpoints hit

All calls target the drive belonging to the configured site. The URL
shape is either `/sites/{site-id}/drives/{drive-id}/...` when
`SHAREPOINT_DRIVE_ID` is set, or `/sites/{site-id}/drive/...` (the
site's default document library) otherwise.

| Backend method | Graph endpoint |
|---|---|
| `save(path, bytes)` | `PUT /root:/{path}:/content` |
| `get(path)` | `GET /root:/{path}:/content` |
| `exists(path)` | `GET /root:/{path}:` |
| `list(prefix)` | `GET /root:/{prefix}:/children` |
| `delete(path)` | `DELETE /root:/{path}:` |
| `make_dir(path)` | `POST /root:/{parent}:/children` with `{name, folder:{}}` per segment |
| `delete_dir(path)` | `DELETE /root:/{path}:` (Graph recursively deletes folders) |

Paths are URL-encoded per segment (`Requirement Analysis` becomes
`Requirement%20Analysis`) before hitting Graph.

### Auth flow (app-only, client credentials)

```
+--------+       (1) POST /oauth2/v2.0/token       +-----------------+
| Backend| ------------------------------------->  | AAD token EP    |
| (MSAL) |     client_id + client_secret +         | (login.micro-   |
|        |     scope="graph/.default"              |  softonline)    |
|        | <-------------------------------------  |                 |
|        |     (2) access_token, expires_in        +-----------------+
|        |
|        |     (3) Authorization: Bearer <token>   +-----------------+
|        | ------------------------------------->  |   Graph API     |
|        | <-------------------------------------  |                 |
+--------+     (4) drive-item response             +-----------------+
```

The token is cached in-process and reused for every Graph call until 5
minutes before its stated expiry (see `TOKEN_REFRESH_MARGIN_SECONDS` in
`backend/app/storage/sharepoint.py`). No refresh tokens — the client
credentials flow doesn't use them; we just re-run step (1) when the
cached token is close to expiring.

## Config

Set in `backend/.env` (see `backend/.env.example` for the full block):

| Env var | Required? | What it is |
|---|---|---|
| `STORAGE_BACKEND` | yes | `local` (default) or `sharepoint`. |
| `SHAREPOINT_TENANT_ID` | when `sharepoint` | Azure AD Directory (tenant) ID. |
| `SHAREPOINT_CLIENT_ID` | when `sharepoint` | Application (client) ID of the AAD app. |
| `SHAREPOINT_CLIENT_SECRET` | when `sharepoint` | Client secret **value** (not ID). |
| `SHAREPOINT_SITE_ID` | when `sharepoint` | Graph composite site ID: `<host>.sharepoint.com,<site-guid>,<web-guid>`. |
| `SHAREPOINT_DRIVE_ID` | no | Specific drive/library. If blank, the site's default document library is used. |
| `SHAREPOINT_ROOT_PATH` | no | Optional folder prefix inside the drive (e.g. `DeliveryAgent`). Sandboxes this app's writes. |

If `STORAGE_BACKEND=sharepoint` and any of the four required vars are
missing, `app/deps.py` raises `RuntimeError` at first factory call and
names every missing variable — the failure surfaces at startup, not on
the first user upload.

## How to test locally (personal tenant)

You need an AAD tenant you own (a free Microsoft 365 developer tenant works)
and a SharePoint site you can grant the app access to.

1. **Register an app in Azure AD**
   - Azure Portal -> Azure Active Directory -> App registrations -> New registration.
   - Name: anything (e.g. `RAG-Agent-Storage-Dev`).
   - Supported account types: Single tenant.
   - Redirect URI: leave blank (client credentials flow doesn't need one).

2. **Add the Graph API permission**
   - Inside the app -> API permissions -> Add a permission -> Microsoft Graph.
   - **Application permissions** (not Delegated) -> `Files.ReadWrite.All`.
   - Back on the API permissions page: click **Grant admin consent for
     `<tenant>`**. This step is mandatory; app-only Graph scopes will not
     work without it. Only a Global Admin can click it.

3. **Create a client secret**
   - Inside the app -> Certificates & secrets -> Client secrets -> New.
   - Copy the **Value** immediately (it's shown once) — this is
     `SHAREPOINT_CLIENT_SECRET`.

4. **Grab the site ID via Graph Explorer**
   - Sign in to <https://developer.microsoft.com/graph/graph-explorer>.
   - Run: `GET https://graph.microsoft.com/v1.0/sites/{host}:/sites/{site-path}`
     e.g. `GET .../sites/contoso.sharepoint.com:/sites/DeliveryAgent`.
   - Copy the `id` field — it looks like
     `contoso.sharepoint.com,11111111-2222-3333-4444-555555555555,66666666-7777-8888-9999-000000000000`.
     That's `SHAREPOINT_SITE_ID`.

5. **Fill in `backend/.env`**
   ```
   STORAGE_BACKEND=sharepoint
   SHAREPOINT_TENANT_ID=<Directory (tenant) ID>
   SHAREPOINT_CLIENT_ID=<Application (client) ID>
   SHAREPOINT_CLIENT_SECRET=<secret value from step 3>
   SHAREPOINT_SITE_ID=<composite ID from step 4>
   SHAREPOINT_ROOT_PATH=DeliveryAgent
   ```

6. **Start the backend**. First upload/download will call MSAL, get a
   token, and go straight to Graph. If auth fails you'll see a clear
   `RuntimeError` in the server log naming the AAD error.

## IT asks (for the Marlabs production tenant)

Everything below has to happen in the actual Marlabs Azure tenant — this
project can't do any of it from the outside.

1. **App registration in the Marlabs AAD tenant** for this workload.
   Owner should be the delivery-agent team. Provide the Directory
   (tenant) ID and Application (client) ID back to us.

2. **Microsoft Graph permission**: `Files.ReadWrite.All` as an
   **Application permission** (not Delegated). Delegated variants need a
   signed-in user and will not work for a headless service.

3. **Global Admin consent** granted on that permission. Application-permission
   Graph scopes are inert until admin-consented; this is a hard requirement,
   not a nice-to-have.

4. **The target SharePoint site + drive**: which site (URL) and which
   document library the agent should write to. We'll derive
   `SHAREPOINT_SITE_ID` via `GET /sites/{host}:/{site-path}` in Graph
   Explorer; IT just needs to confirm the site path and that our app
   registration has access to it (either tenant-wide via Graph app perms,
   or narrowed via Sites.Selected + a per-site grant if IT prefers
   least-privilege — call this out and we'll switch to `Sites.Selected`
   if requested).

5. **Client secret rotation policy**: AAD lets secrets last 6-24 months.
   We need to know:
   - Rotation cadence (default: 12 months).
   - Who owns the calendar entry to rotate before expiry.
   - Where the current secret should be stored (e.g. Azure Key Vault vs
     the app's env file) and who is on the distribution list for the
     new value.

6. **Conditional Access**: confirm no CA policy blocks app-only Graph
   calls from wherever this backend runs (the runtime's outbound IPs
   / geography / device state). App-only tokens can't satisfy MFA or
   device-compliance CA rules, so a policy that requires those will
   silently break the app.

7. **Egress firewall / IP allowlisting**: if Marlabs uses an outbound
   firewall between the runtime and SharePoint, allowlist
   `graph.microsoft.com` and `login.microsoftonline.com` from our
   runtime's egress IPs (share those with IT once the deploy target is
   fixed).

## Trade-offs and known limits

- **Simple upload only**: `save()` uses PUT `.../content`, which Graph caps
  at ~250 MB per file. If the agent ever needs to store bigger files
  we'll need the upload-session flow.
- **`list()` is non-recursive**, matching the `StorageBackend` contract
  and `LocalFilesystemStorage` behaviour. Callers that need recursion
  should walk the tree.
- **No file locking / ETag concurrency control**. Two simultaneous
  `save()` calls to the same path race; last write wins. Same behaviour
  as the local backend, so this is a parity trade rather than a
  regression.
- **In-process token cache** — every worker/process fetches its own
  token from AAD. Fine for a handful of workers; if this grows to
  dozens of pods we'd want a shared cache (Redis) to avoid hammering
  the token endpoint.
