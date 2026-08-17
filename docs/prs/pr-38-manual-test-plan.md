---
title: "PR #38 manual test plan"
pr_number: 38
pr_url: https://github.com/Marlabs-Innovations-Private-Limited/RAG-agent/pull/38
apparatus_pr: (companion — feat/pr-38-test-apparatus)
---

# PR #38 — manual test protocol

Automated coverage lives in the companion `test/pr-38-apparatus` branch (~30
new deterministic tests) plus PR #36 (agent-trajectory suite, 21 scenarios)
and PR #35 (RAG-quality suite, 15 scenarios). This doc covers what those
tests can't verify — the UI redesign and the human-facing chat flows.

**Time budget:** ~15 minutes.

## Prerequisites

- App running locally: `cd frontend && npm run dev` (backend on :8000, frontend on :5173).
- Fresh DB or `alembic upgrade head` already applied (4 new tables).
- Seed data present (`python -m app.db.seed`, `python -m app.db.seed_templates`).
- A real (or fake-but-plausible) SOW document handy for the SOW workflow test.

## Chat UI redesign (must pass)

- [ ] Sidebar renders on the left; collapse chevron reachable on the edge.
- [ ] Toggling the sidebar animates smoothly; chat panel width adjusts.
- [ ] The **upload panel is gone** (folded into a different flow).
- [ ] Chat panel is unboxed — assistant replies flow as plain text, not in bubbles-inside-bubbles.
- [ ] Auto-grow input expands as you type; caps at a reasonable max height.
- [ ] Marlabs avatar shows on assistant messages.
- [ ] New-chat greeting reads warmer than the old static text.
- [ ] Sending a long message → **only the chat area scrolls**, not the whole viewport.
- [ ] Status cards render with elevation + differentiated bubble widths.
- [ ] Modern scrollbar styling in chat.

## Tool-activity in-progress phase (new in PR #38)

- [ ] Send a message that triggers a tool call (e.g. `list phases`).
- [ ] A brief "in progress" or "thinking" state renders BEFORE the result appears.
- [ ] Result settles cleanly (no flash-of-partial-content).

## Document version history (new feature)

- [ ] Upload a document (e.g. Acme's Kickoff) once → download link works.
- [ ] Upload the SAME `client × doc_type` again with different content.
- [ ] Ask chat "show version history for Acme's Kickoff" → **both versions listed** with individual download links.
- [ ] Search view shows a **version count badge** (`v2`) on the doc row.
- [ ] Download the older version → matches the first upload's bytes (not the newest).

## SOW extraction (headline feature)

- [ ] Upload a SOW-shaped document for a new client (`Acme` — reuse the seed).
- [ ] Ask chat "who's the project team for Acme?" → response cites team members WITHOUT re-reading the doc (should be fast, not a 5-second LLM call).
- [ ] Ask "who owns the MSA for Acme?" → returns document owner from the SOW extraction.
- [ ] Ask "who needs to approve the SOW for Acme?" → returns approver.
- [ ] Ask "summarize the SOW for Acme" → all four fields (project name, team, owner, approver) appear — none silently omitted.

## Approval-chase reminder flow (new)

- [ ] Ask "draft an approval reminder for the Acme MSA".
- [ ] Assistant asks for explicit confirmation before drafting — do NOT auto-draft.
- [ ] Confirm → a proper reminder message is produced (with the approver named).
- [ ] Deny → no message drafted, agent acknowledges.

## Not-applicable flag (new)

- [ ] Mark a phase-2 doc for Acme as "not applicable" via chat.
- [ ] Try to request a phase-3 template for Acme → gate lets you proceed (doesn't stall on the N/A doc).
- [ ] Unmark the doc → gate re-engages as expected.
- [ ] Attempt to unmark with a slightly-wrong doc name → agent self-corrects instead of silent no-op.

## Regression scenarios (must NOT break)

- [ ] `list phases` — still works, returns all 7 phases.
- [ ] Upload a NON-SOW doc → no SOW-extraction attempted.
- [ ] Try to request a phase-3 template when phase-2 is incomplete AND no N/A flag set → **gate still blocks**.
- [ ] Delete a client via chat → still asks for confirmation before soft-delete.
- [ ] Chat history persists across page reloads (localStorage).

## Anti-fabrication (new agent-hygiene fix)

- [ ] Ask "give me the download link for a doc that doesn't exist" → assistant refuses / says it can't find it. Does NOT invent a URL.
- [ ] Ask about a made-up doc_type ("give me the WBS for Acme") → agent asks for clarification via guided doc discovery. Does NOT fabricate.
- [ ] In one conversation, do action A → then a follow-up that could benefit from stale results → assistant re-checks instead of trusting the old result.

## Sign-off

Reviewer initials + date once all checkboxes pass:

```
Reviewer:  ____________________________________
Date:      ____________________________________
Verdict:   [ ] promote to main   [ ] block — see comments
```
