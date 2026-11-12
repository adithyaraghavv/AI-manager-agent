# Delivery Manager Agent (Copilot Studio) — build log

This is a **separate system** from the FastAPI/React app documented elsewhere in
this repo. It's a Microsoft Copilot Studio agent ("Delivery Manager Agent") sitting
on top of a real SharePoint document library, built using Copilot Studio's own
skill/instruction editor — there is no source-controlled code for it, so this file
is the written record of what was built, fixed, and is still open.

## SharePoint structure

- `Clients/<ClientName>/<phase folder>` — active client documents
- `Recycle Bin/<ClientName>/<phase folder>` — soft-deleted documents
- Phase folders: `01_Pre-requisites`, `02_Requirement Analysis`, `03_System Design`,
  `04_Implementation (Coding)`, `05_Testing (STLC Integrated)`, `06_Deployment`,
  `07_Maintenance` — same 7 phases as the coded app's `sdlc_phase_config.json`.
- A client's phase folders are meant to exist as a **fixed set of 7**, whether or
  not documents have been filed into them yet (see create-client-skill /
  upload-document-skill below).

## Skills built or fixed this round

| Skill | What it does |
|---|---|
| `upload-document-skill` | Validates file type, detects/confirms document type, resolves client (case-insensitive), enforces phase-gating (same rule as the coded app), versions filenames (`v<N>_Marlabs_<DocType>_<Client>_<Timestamp>`), and — if the client is brand-new — creates all 7 phase folders upfront before uploading, not just the one needed. |
| `create-client-skill` | Creates a brand-new client with all 7 phase folders upfront when no document is attached (e.g. "create client Tuesday"). Hands off to upload-document-skill if a file is attached instead. |
| `backfill-phase-folders-skill` | One-time/on-demand skill to retroactively create any missing phase folders for existing clients (or all clients), without touching anything already there. |
| `delete-client-skill` | Soft-deletes a client: moves every document, phase by phase, **file by file** (not a folder-level move) from `Clients/<Client>/<phase>` to `Recycle Bin/<Client>/<phase>`, after explicit PM confirmation. Reports partial failures precisely rather than claiming full success. |
| `restore-client-skill` | The mirror of delete-client-skill — moves everything back from Recycle Bin to Clients, file by file, after confirmation. |
| `summarize-document-skill` | Summarizes a filed document's actual content (SOW gets a structured summary: value, dates, team, approvers; everything else gets a plain-English summary). Defaults to the latest version silently when multiple exist, only asking when two versions share the exact same timestamp. |
| `answer-document-question-skill` | Answers a specific question about a document's content, grounded in SharePoint knowledge search. Same latest-version-by-default rule as summarize-document-skill. |
| `approval-reminder-skill` | Looks up who approves a given document type per the client's SOW, offers to draft a reminder message. Same latest-version-by-default rule. |
| `delete-document-skill` / `restore-document-skill` | Pre-existing, single-document soft delete/restore — the proven per-file-move pattern that delete-client-skill and restore-client-skill were rewritten to match. |
| `mark-not-applicable-skill` | Pre-existing — marks a document as not applicable for a client so it stops showing as missing. |

## Bugs found and fixed

1. **Stray "Shared Documents" duplicate-path folders.** Folder-level moves in the
   original delete-client-skill/restore-client-skill occasionally produced a
   duplicated, empty `Shared Documents/Shared Documents/...` path. Root cause:
   folder-level moves instead of per-file moves. Fixed by rewriting both skills
   to move files individually (matching delete-document-skill's already-reliable
   pattern) and removing an over-corrected "Shared Documents" path guard that
   briefly caused false refusals on legitimate deletes (confirmed via repeated
   Lilly/SiriusXM/WestPharma/Markel test cycles in both preview and evaluate mode).
2. **Version-selection inconsistency.** summarize-document-skill,
   answer-document-question-skill, and approval-reminder-skill would sometimes
   stop and ask "which version?" even when the PM hadn't asked about a specific
   one. Fixed: default silently to the latest version (by filename version
   number / last-modified date) unless two versions share the exact same
   timestamp, and always state which version was used.
3. **New clients only got the one phase folder being uploaded into**, not the
   full 7-phase skeleton — lazy folder creation was the original (undesired)
   behavior. Fixed via upload-document-skill's new-client checklist step and the
   new create-client-skill / backfill-phase-folders-skill.

## Test clients used for end-to-end validation

- **Lilly, SiriusXM, WestPharma, Apple, TestClientXYZ, TestCompare** — pre-existing
  demo clients used throughout testing (delete/restore cycles, version diffs,
  gating, summarization).
- **Markel** — built specifically for a full end-to-end pass: all 24 required
  documents across all 7 phases generated from the real Word templates, with SOW,
  Approved HLD, and Deployment Plan each given two genuinely different versions
  (contract value, scope, go-live date, release manager) to validate
  version-defaulting and version-diff questions.
- **Phoenix, "seven," "friday"** — throwaway clients created during upload-flow
  and create-client-skill testing; safe to delete if still present.

## Evaluate-mode test sets

CSV eval sets were built covering: delete/restore client (multiple clients, with
a repeated cycle to stress-test the per-file-move fix), and the version-defaulting
fix (summarize/answer/approval across clients with multiple document versions,
plus an explicit v1-vs-v2 diff question). A couple of early evaluate-mode
failures turned out to be the agent second-guessing itself over the
since-removed "Shared Documents" guard rather than real bugs — confirmed by
cross-checking against preview mode, which passed consistently.

## Open issue: Teams deployment

The agent is published with the **Teams + Microsoft 365** channel added, and
works correctly via **Microsoft Copilot** (tested, got real responses). It does
**not** work via **Microsoft Teams** — 0 sessions/messages logged in Copilot
Studio's Monitor tab for anyone, including the agent owner, even via the
in-product "View in Microsoft Teams" button. Removing and re-adding the Teams
channel, and republishing, did not fix it.

Since Copilot works but Teams doesn't, this isolates the problem to the **Teams
app-installation permission layer**, not the agent, its auth, or its backend.
Per Microsoft's own documentation, Teams requires an org-level setting allowing
**Power Platform / custom apps** to be installed before any Copilot
Studio-built agent can function there — a setting controlled in the Teams Admin
Center (Teams apps → Permission policies / "Manage Power Platform apps"), not
from inside Copilot Studio. This needs to be checked/enabled by someone with
Teams admin access; nothing further can be diagnosed or fixed from the builder
side until that's confirmed.
