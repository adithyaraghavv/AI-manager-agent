# Delivery AI Agent — Discovery Documentation

**Marlabs — Delivery Team Automation Initiative**

*Source: Discovery call between Tarun Prem Sai Singana and Adithya Raghav V | Compiled: 29 July 2026*

---

## 1. Overview

Hames (delivery team) has requested an AI agent to support project managers — new or existing, on new or existing client engagements — with the document lifecycle that a project must move through from kickoff to delivery. The problem being solved is process/document sprawl: templates for MSA, SOW, HLD, LLD, BRD, SRS, RTM and similar deliverables currently exist across Marlabs but are scattered with no consistent naming convention, folder structure, or central storage location. Every client folder is organized differently today, which makes it hard for a PM — especially a new one — to know what documents are required at each stage, where to find the right template, and where to file the completed version.

## 2. Objective

Build a conversational AI agent for project managers that:

- Acts as a single point of contact for the standard project document lifecycle.
- Knows which documents belong to which phase of a project.
- Serves the correct template on request, and enforces basic phase-gating (e.g. won't hand out a pricing template until MSA/SOW exist).
- Automatically files completed documents into the right client folder and the right phase sub-folder — creating that structure on the fly for a brand-new client if it doesn't exist yet.
- Removes the need for PMs to manually hunt through inconsistent folder structures across clients.

## 3. Current Process — Project Phases & Required Documents

Confirmed via the official phase configuration reference (`sdlc_phase_config.json`) provided by Tarun/Hames — this is the authoritative 7-phase structure the AI agent's gating logic is built against. Each phase lists the documents required before the project can move to the next phase; the first four phases (Pre-requisites through Implementation) were also independently confirmed in the discovery call.

| Seq | Phase | Required documents (to move to the next phase) |
|---|---|---|
| 1 | Pre-requisites | MSA; SOW; Pricing; Kick-off Deck; Kick-off Meeting Invite |
| 2 | Requirement Analysis | Business Requirement Document (BRD); Stakeholder Approvals; Clear Scope Definition |
| 3 | System Design | Approved SRS; RTM Updated; Architecture Feasibility Study |
| 4 | Implementation (Coding) | Approved HLD; Approved LLD; Development Environment Setup; Coding Standards Defined |
| 5 | Testing (STLC Integrated) | Approved Test Plan; Test Environment Ready; Test Data Prepared |
| 6 | Deployment | Signed-off Test Summary Report; Release Notes; Deployment Plan |
| 7 | Maintenance | Deployed System in Production; SLA Agreements; Support Plan |

> *This configuration file appears to be the actual machine-readable source the agent should reference for phase-gating logic — worth confirming with Tarun/Hames whether it is already wired into the POC or still needs to be integrated.*

## 4. How the AI Agent Is Meant to Work

This is the end-to-end interaction flow as walked through live in the demo:

- Project Manager (new or existing project, new or existing client) initiates a conversation with the AI agent.
- The AI agent greets the PM conversationally (a chatbot-style interface) and asks how it can help.
- The PM asks for a specific template — e.g. "I'm starting a new project with Hillenbrand, can I get the pricing template?"
- The agent enforces phase-gating logic before serving a document. Before releasing a pricing template it checks whether prerequisite documents (MSA, SOW) already exist for that client — if not, it withholds the pricing template.
- If prerequisites are satisfied, the agent fetches the requested template from a central master template folder and gives the PM a downloadable file (not just a link/path).
- The PM downloads the template, fills it in outside the tool, and re-uploads the completed document back to the agent (e.g. "here is the completed pricing document, please file this").
- The agent checks whether a folder already exists for that client. If not, it creates a new client folder with the full standard sub-folder structure (one sub-folder per phase).
- The agent places the uploaded document into the correct phase sub-folder for that client automatically (e.g. a completed/approved HLD is filed under the Implementation phase, not Requirement Analysis).
- This gating is a hard block, not just a warning: if a PM tries to upload a later-phase document (e.g. HLD) before all earlier-phase documents exist for that client, the agent refuses the upload and instead offers to provide the missing earlier-phase templates first, so the PM can complete those before proceeding.
- Files are named using a fixed convention: `Marlabs_<DocType>_<ClientName>_<Timestamp>` — confirmed live in the demo on the stored HLD file.

**Underlying storage model (as sketched by Tarun):**

- A single master template folder holding one canonical copy of every document template (SOW, pricing, BRD, SRS, HLD, LLD, etc.).
- A separate "clients" folder containing one sub-folder per client, each replicating the full phase structure (Pre-requisites, Requirement Analysis, System Design, Implementation, ...).
- When a PM uploads a completed document for a client that doesn't have a folder yet, the agent creates the client folder and the full phase sub-structure automatically, then files the document into the correct phase.
- Storage today is local (the POC was demoed storing data on Tarun's machine). The intended end state is for this to live in SharePoint / the cloud, not locally — flagged explicitly by Tarun as a required next step, not yet built.

> *This master-folder / per-client-folder model is also confirmed in a separate reference document (`Database_structure.docx` / `Database_structure.md`) shared by Tarun, which shows a master Template folder alongside a Clients folder containing one sub-folder per client (e.g. Client 1, Client 2, Client 3), matching the live demo.*

This was originally conceived internally as a "RAG agent" (retrieval-augmented generation) — the agent retrieves the right template/document from the template store rather than generating content from scratch. Whether a full RAG pipeline is actually needed is currently an open question (see Section 7) now that a team member ("Others") who was driving that direction has left.

## 5. Current Build Status (Proof of Concept)

A working skeleton/POC already exists, built by Tarun and a former team member ("Others", an intern who has since left):

- A working demo was shown live: requesting a pricing template, filling it, uploading it back, and the agent correctly filing it under the right client and phase, with correct file naming (Marlabs + doc type + client + timestamp).
- Folder/hierarchy logic is functionally done: the agent correctly creates a new client folder with full phase sub-structure when needed, and enforces phase-gating as a hard block on both template requests and uploads (confirmed live for both the pricing/MSA-SOW case and the HLD case).
- The POC was initially built with access to only 5 of the required templates; broader template access has since been granted (some templates are still being uploaded by the delivery team on an ongoing basis).
- UI is currently a rough, unstyled placeholder ("white-coded"/default styling) — functional but explicitly flagged by Tarun as needing a cleanup pass.
- Data storage is local only right now, not yet in SharePoint/cloud as intended (see Section 4).
- Code currently lives in Azure DevOps (ADO) — organized into backend, frontend, and template folders, with a README describing the architecture. There is also a supporting folder ("PMDM Enable") containing stack/architecture documentation for the agent.
- A database layer was planned, tentatively using PostgreSQL, but final data-layer design is unresolved (see open questions).
- Development so far has been "vibe-coded": the former team member ("Others") wrote rough initial code by hand, and he and Tarun then worked through it together with Claude to iterate and refine it — done in joint working sessions rather than a formal spec-driven process.
- Timeline pressure: Hames wants this delivered in roughly 3–4 weeks from the time of this call.

## 6. Tooling, Access & Environment Notes

- The existing codebase is in Azure DevOps. Marlabs previously used GitHub for this and other accelerator projects but was directed to migrate everything to ADO.
- Plan going forward: get Adithya access to the ADO repo, clone/replicate it into a personal or Marlabs GitHub repo, build and iterate there via feature branches, review with Hames, then merge back into an ADO repo under the Marlabs org once approved.
- Adithya's proposed branch workflow (agreed on the call): push the existing ADO code to GitHub, then work off two branches — Tarun's main branch and Adithya's working branch. Adithya makes changes on his branch, shares it back, Tarun reviews, and merges into main once approved.
- Adithya does not currently have access to the ADO repo or the SharePoint/templates folder — Tarun has asked Hames to grant this access (Hames was on leave at the time of the call).
- Known blocker: Claude (both in VS Code and via Google Chrome) is blocked on Adithya's corporate laptop/network in India. Workaround discussed: Adithya can view/sync changes another way (e.g. via a personal machine or an existing setup shown on the call), since this same network restriction affected earlier work as well.
- GitHub Copilot remains usable in VS Code as an alternative, alongside whatever Claude access route is worked out.
- Planned working cadence: short daily/regular working sessions (similar to the ~30-minute daily calls Tarun previously had with the former team member) once access is sorted out.

## 7. Open Questions

- Do we actually need a full RAG pipeline, or can this be solved with simpler structured retrieval + file placement logic? Flagged explicitly as unresolved now that the original proponent of the RAG approach has left the team.
- Final database/data-layer decision — PostgreSQL was the initial assumption, but this was not confirmed as final on the call.
- Repo strategy — final call on ADO vs. GitHub for the working repo, and the branch/merge process, needs to be confirmed once ADO access is granted.

## 8. Immediate Action Items

- Hames to grant Adithya access to: the ADO repository and the SharePoint templates/documents folder.
- Tarun to locate a prior handover document written by the former team member ("Others") before leaving.
- Adithya to review the existing ADO codebase (backend, frontend, templates, README) once access is granted, and replicate it into GitHub for iterative development.
- Resolve the Claude/VS Code network access blocker so Adithya can work effectively.
- Decide on the RAG-vs-simpler-retrieval approach and finalize the database choice.
- Migrate storage from local to SharePoint/cloud.
- Clean up the UI (currently unstyled placeholder).
- Set up a recurring short working session cadence with Tarun (and Hames once available) to keep momentum, targeting Hames's ~3–4 week delivery expectation.

## 9. Gaps in This Documentation

One portion of the original call recording is still not available in the transcript provided and may contain relevant detail:

- ~34:34–37:21 — further detail on the proposed daily/working-session cadence.

> *If this section becomes available, it should be reviewed and this document updated accordingly.*
