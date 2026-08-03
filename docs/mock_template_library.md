# Mock Template Library (until SharePoint access is granted)

We don't yet have access to the real SharePoint template library
(`AI_Agent_Discovery_Documentation.md`, section 8). This document covers the
temporary stand-in used for local/dev testing and demoing, and exactly what
changes when real SharePoint access lands.

## 1. Proposed structure

The mock library lives under the local `/templates` folder (path configurable
via `TEMPLATE_STORE_PATH` in `.env`) and mirrors the same phase hierarchy used
for client folders, so the structure matches what production will look like:

```
templates/
  01_Pre-requisites/
    MSA.txt
    SOW.txt
    Pricing.txt
    Kick_off_Deck.txt
    Kick_off_Meeting_Invite.txt
  02_Requirement Analysis/
    Business_Requirement_Document_BRD.txt
    Stakeholder_Approvals.txt
    Clear_Scope_Definition.txt
  03_System Design/
    Approved_SRS.txt
    RTM_Updated.txt
    Architecture_Feasibility_Study.txt
  04_Implementation (Coding)/
    Approved_HLD.txt
    Approved_LLD.txt
    Development_Environment_Setup.txt
    Coding_Standards_Defined.txt
  05_Testing (STLC Integrated)/
    Approved_Test_Plan.txt
    Test_Environment_Ready.txt
    Test_Data_Prepared.txt
  06_Deployment/
    Signed_off_Test_Summary_Report.txt
    Release_Notes.txt
    Deployment_Plan.txt
  07_Maintenance/
    Deployed_System_in_Production.txt
    SLA_Agreements.txt
    Support_Plan.txt
```

Generated (and re-runnable) by `python -m app.db.seed_templates`.

## 2. Dummy template documents

All 20 required document types from `config/sdlc_phase_config.json` get a
placeholder `.txt` file with a short mock-content note inside, plus a
`templates` DB row (`doc_type`, `storage_path`, `filename`) so the exact same
lookup path (`request_template()` in `app/services/document_service.py`) that
will serve real SharePoint files works identically today.

## 3. Configuration

No new configuration was needed — this was already designed to be
config-driven:

| Setting | Current (mock) | Production (later) |
|---|---|---|
| `TEMPLATE_STORE_PATH` (`.env`) | `../templates` (local folder) | SharePoint-backed path/URL |
| Storage backend (`app/deps.py::get_template_storage`) | `LocalFilesystemStorage` | `SharePointStorage` (new class, same `StorageBackend` interface) |
| `templates` DB table | Seeded by `app/db/seed_templates.py` (mock files) | Seeded by an equivalent script pointing at real SharePoint files, or updated directly |

## 4. Test plan (already executed against this build)

1. **Download a phase-1 template** (e.g. Pricing) for a brand-new client name
   → expect `200`, mock file content returned.
2. **Request a phase-2 template** (e.g. BRD) before any phase-1 docs are filed
   → expect `409`, with the exact list of missing phase-1 documents.
3. **Upload all 5 phase-1 documents** for that client
   → expect `200` on each, filed under `<client>/01_Pre-requisites/` with the
   `Marlabs_<DocType>_<ClientName>_<Timestamp>` naming convention.
4. **Re-request the phase-2 template** → now expect `200`.
5. **Request a phase-3 template** (e.g. Approved SRS) → expect `409` still,
   since only the phase-2 *template* was downloaded, not filed — confirms the
   system tracks filed/uploaded documents, not merely requested ones.

All five steps were run against a live instance of this build (Postgres +
local storage) and passed exactly as expected.

## 5. Gaps, risks, recommendations before production

- **No code depends on the real SharePoint location.** Confirmed by re-reading
  every call site that touches template storage — all of them go through
  `StorageBackend` and the `templates` DB table, never a hardcoded path.
  Swapping to production is a data/config change, not a code change.
- **Placeholder files are `.txt`, not real Office documents.** Fine for
  testing the request/gate/upload mechanics, but don't demo the *content* of
  a template as if it were real — say explicitly it's a mock file if asked.
- **No `SharePointStorage` implementation exists yet** — it needs writing
  once SharePoint API access/credentials are available (likely via Microsoft
  Graph API). This is net-new work, not a config flip, so don't assume it's a
  same-day swap once access lands.
- **Template versioning isn't handled** — `templates` table has one row per
  `doc_type`; a re-seed with `--force` overwrites in place rather than
  keeping history. Fine for a POC; worth a real decision before production if
  templates get revised over time.
