# Workflow

How a document moves through the system, and how the chat agent, the dashboard,
and the hard-block gating logic all fit together.

## 1. Client document lifecycle (the 7 phases)

Every client moves through the same fixed, ordered set of phases. A phase can't
be entered until every required document from every earlier phase already
exists for that client — enforced server-side in
`backend/app/services/document_service.py`, not just suggested by the chat agent.

```mermaid
flowchart TD
    A["1. Pre-requisites<br/>MSA, SOW, Pricing,<br/>Kick-off Deck, Kick-off Meeting Invite"] --> B
    B["2. Requirement Analysis<br/>BRD, Stakeholder Approvals,<br/>Clear Scope Definition"] --> C
    C["3. System Design<br/>Approved SRS, RTM Updated,<br/>Architecture Feasibility Study"] --> D
    D["4. Implementation (Coding)<br/>Approved HLD, Approved LLD,<br/>Dev Environment Setup, Coding Standards"] --> E
    E["5. Testing (STLC Integrated)<br/>Approved Test Plan, Test Environment Ready,<br/>Test Data Prepared"] --> F
    F["6. Deployment<br/>Signed-off Test Summary Report,<br/>Release Notes, Deployment Plan"] --> G
    G["7. Maintenance<br/>Deployed System in Production,<br/>SLA Agreements, Support Plan"]

    style A fill:#283B91,color:#fff
    style B fill:#283B91,color:#fff
    style C fill:#283B91,color:#fff
    style D fill:#283B91,color:#fff
    style E fill:#283B91,color:#fff
    style F fill:#283B91,color:#fff
    style G fill:#283B91,color:#fff
```

## 2. Template request / document upload — the gating decision

This is the actual decision tree that runs every time someone (PM or chat agent)
asks for a template or tries to upload a document. The agent and the raw API hit
the exact same check, so the agent can't talk its way around a block.

```mermaid
flowchart TD
    Start(["PM asks for a template<br/>or uploads a document"]) --> Resolve["Resolve client name<br/>(case-insensitive)"]
    Resolve --> Found{"Client found?"}
    Found -- "No, and doc belongs to Phase 1" --> NewClient["Treat as brand-new client,<br/>continue"]
    Found -- "No, and doc belongs to Phase 2+" --> Refuse1["Refuse:<br/>client not found"]
    Found -- Yes --> Lookup["Get existing documents<br/>for this client"]
    NewClient --> Lookup
    Lookup --> Phase["Determine target phase<br/>for this document type"]
    Phase --> Check{"Every required doc from<br/>every EARLIER phase present?"}
    Check -- No --> Refuse2["Refuse upload/template.<br/>Report exactly what's<br/>missing and which phase<br/>is blocking"]
    Check -- Yes --> Allow["Allow.<br/>Template: return file.<br/>Upload: version + file,<br/>confirm client/type/phase/version"]

    style Refuse1 fill:#b91c1c,color:#fff
    style Refuse2 fill:#b91c1c,color:#fff
    style Allow fill:#15803d,color:#fff
```

## 3. Client deletion — human-in-the-loop, always

The AI can look a client up and summarize what deleting them would do, but it
can never perform the deletion itself. Only a human clicking "Confirm" in the
UI can make that true — the agent has no way to know whether that click happened.

```mermaid
flowchart TD
    A["PM: 'delete client X'"] --> B["Agent calls propose_delete_client"]
    B --> C["Agent shows client info:<br/>phases complete, document count"]
    C --> D["Confirm/cancel card<br/>rendered in the UI"]
    D -- "PM clicks Cancel" --> E["Nothing happens.<br/>Confirmation message shown."]
    D -- "PM clicks Confirm" --> F["Human-triggered delete:<br/>documents, DB record,<br/>storage folder removed"]

    style D fill:#283B91,color:#fff
    style F fill:#b91c1c,color:#fff
    style E fill:#15803d,color:#fff
```

## 4. Manager dashboard — stale detection

Read-only aggregation, no gating logic of its own — it just reports what the
gating/service layer already knows about every client at once.

```mermaid
flowchart LR
    A["GET /api/clients/status"] --> B["For each client:<br/>phase progress,<br/>blocking phase,<br/>missing documents"]
    B --> C{"No document uploaded<br/>in stale_after_days<br/>(default 3)?"}
    C -- Yes --> D["Flag as stale.<br/>'Copy reminder' button<br/>generates a draft message"]
    C -- No --> E["Shown normally,<br/>no flag"]
```

## Where each piece lives

| Step | Code |
|---|---|
| Phase/document config (source of truth) | `config/sdlc_phase_config.json` |
| Hard-block gating | `backend/app/services/document_service.py` |
| Chat agent tool definitions | `backend/app/agent/tools.py` |
| Chat turn orchestration | `backend/app/agent/orchestrator.py` |
| Storage abstraction (swap-in SharePoint later) | `backend/app/storage/base.py` |
| Dashboard / stale flagging | `backend/app/services/dashboard_service.py` |
