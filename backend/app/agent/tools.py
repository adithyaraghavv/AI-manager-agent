"""Tool definitions for the conversational layer (OpenAI-style function-calling
schema, used by the OpenAI API).

These tools only ever call into app.services / app.core — never storage or
the DB directly — so the same hard-block gating guarantees apply whether a
document flows through the API or through the chat agent.

Binary uploads are intentionally NOT a tool here: pushing file bytes through
an LLM tool-call is unnecessary and wasteful. The agent's job is to have the
conversation and tell the PM which REST endpoint to upload to (or the
frontend attaches the file directly to POST /api/clients/{client}/documents);
the actual write always goes through app.services.document_service directly.
"""
from typing import Any

from app.core.document_lookup import find_document_types
from app.core.gating import missing_documents, resolve_phase_for_document
from app.core.phase_config import PhaseConfig
from app.db.rest_client import SupabaseRestClient
from app.services import embedding_service
from app.services.client_service import (
    existing_document_types,
    find_client,
    get_or_create_client,
    mark_document_not_applicable,
    not_applicable_document_types,
    satisfied_document_types,
    unmark_document_not_applicable,
)
from app.services.document_service import (
    ClientDocumentNotFound,
    GatingBlocked,
    TemplateFileMissing,
    TemplateNotFound,
    get_document_location,
    list_document_versions,
    request_template,
)
from app.services.sow_extraction_service import (
    SowExtractionFailed,
    generate_approval_reminder,
    get_sow_summary,
)
from app.storage.base import StorageBackend

TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_phases",
            "description": (
                "List all project phases in sequence, with the documents required to complete each one. "
                "Use this when the PM asks what documents are needed, or what phase something belongs to."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_client_status",
            "description": (
                "Get a client's document status: which documents exist, which are missing, and which phase "
                "they are currently blocked on. Use this before telling a PM what they can request or upload next."
            ),
            "parameters": {
                "type": "object",
                "properties": {"client_name": {"type": "string", "description": "The client's name."}},
                "required": ["client_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_template",
            "description": (
                "Request the master template for a document type on behalf of a client. Enforces hard-block "
                "phase-gating: if the client is missing required documents from any earlier phase, this will "
                "refuse and report exactly what's missing instead of returning a template."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_type": {
                        "type": "string",
                        "description": "Exact document type, e.g. 'Pricing', 'Approved HLD'.",
                    },
                    "client_name": {"type": "string", "description": "The client's name."},
                },
                "required": ["doc_type", "client_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_versions",
            "description": (
                "List every version on file for one of a client's documents — oldest to newest, with who "
                "uploaded each one, when, and any change comment. Re-uploading a document never overwrites "
                "an earlier version; every upload is kept permanently. ONLY use this when the PM's own "
                "words are specifically about version history / past uploads (e.g. 'show me the versions', "
                "'what's been uploaded so far', 'the last one someone filed'). A plain 'give me the SOW' / "
                "'I need the HLD' request — even for a document that turns out to have zero uploads yet — "
                "means request_template, NOT this tool; do not call this just to check whether something "
                "exists before deciding what to do."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "client_name": {"type": "string", "description": "The client's name."},
                    "doc_type": {
                        "type": "string",
                        "description": "Exact document type, e.g. 'Approved HLD'.",
                    },
                },
                "required": ["client_name", "doc_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_document_location",
            "description": (
                "Get the FOLDER PATH where an already-filed document lives, without returning a "
                "download link or the file itself. Use this ONLY when the PM explicitly asks where "
                "something is stored / for the folder / to browse it themselves — phrases like 'where "
                "is it', 'what folder', 'just the path', not a plain request to get/download the "
                "document. For an ordinary 'give me the X' request, use request_template or "
                "get_document_versions instead — those hand over the actual file/link."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "client_name": {"type": "string", "description": "The client's name."},
                    "doc_type": {
                        "type": "string",
                        "description": "Exact document type, e.g. 'Approved HLD'.",
                    },
                },
                "required": ["client_name", "doc_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_document_not_applicable",
            "description": (
                "Mark a document type as NOT REQUIRED for a specific client — e.g. 'Requirement "
                "Analysis' doesn't apply because the client already handed over finished requirements "
                "in the SOW. This stops phase-gating from permanently blocking on it: an unfiled but "
                "not-applicable document no longer counts as missing. Use this only when the PM "
                "explicitly says a document/phase doesn't apply, isn't needed, or is out of scope for "
                "this client — never mark something not-applicable just because it hasn't been filed "
                "yet or because a request was blocked on it; that's what request_template/upload are "
                "for. This is reversible (see unmark_document_not_applicable)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "client_name": {"type": "string", "description": "The client's name."},
                    "doc_type": {
                        "type": "string",
                        "description": "Exact document type, e.g. 'Business Requirement Document (BRD)'.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why it doesn't apply, if the PM gave one, e.g. 'client provided finished requirements in the SOW'.",
                    },
                },
                "required": ["client_name", "doc_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "unmark_document_not_applicable",
            "description": (
                "Reverse a previous not-applicable mark — the document type goes back to being "
                "genuinely required and will count as missing again until it's filed. Use this when "
                "the PM says a document that was marked not-applicable actually does apply after all."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "client_name": {"type": "string", "description": "The client's name."},
                    "doc_type": {
                        "type": "string",
                        "description": "Exact document type, e.g. 'Business Requirement Document (BRD)'.",
                    },
                },
                "required": ["client_name", "doc_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_document_types",
            "description": (
                "Search for document types by a loose/partial phrase (e.g. 'SOW', 'test', 'design') "
                "when the PM doesn't know or didn't give the exact document type name. Returns every "
                "real document type that could match, each with its phase. Use this BEFORE calling "
                "request_template or get_document_versions whenever you're not already certain of the "
                "exact document type string — if it returns more than one match, list them for the PM "
                "and ask which one they mean instead of guessing. If it returns exactly one, you can "
                "proceed with that exact string directly."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The PM's rough description of the document, e.g. 'SOW' or 'test plan'.",
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_sow_summary",
            "description": (
                "Pull key facts out of a client's filed SOW — contract value, start date, end date, a "
                "scope summary, the project team (who's assigned and their role), and document "
                "responsibility (who OWNS/provides each document vs. who APPROVES/signs off on it — "
                "SOWs vary on whether those are the same party or different ones) — so the PM doesn't "
                "have to open the document themselves. document_responsibilities entries look like "
                "{'HLD': {'owner': 'Marlabs team', 'approver': 'Client Sponsor'}} — when a SOW names "
                "only one party for a document, owner and approver will be the same value, not a guess. "
                "Use this when the PM asks something the SOW's CONTENT would answer: a specific field "
                "('what's the contract value for Acme', 'who's on the team for Acme', 'who owns the HLD "
                "for Acme', 'who approves the HLD for Acme'), or a general request to summarize/overview "
                "the SOW itself ('summarize the SOW for Acme', 'give me a rundown of Acme's SOW') — not "
                "for a plain 'give me the SOW' request, which means the file itself "
                "(request_template/get_document_versions). Re-reads the SOW fresh every call, so it's "
                "always based on whatever version is currently on file. Any field the SOW doesn't "
                "actually state — including team assignments and document responsibility — comes back "
                "null; never invent a name, role, or responsible party that isn't actually in the "
                "document."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "client_name": {"type": "string", "description": "The client's name."},
                },
                "required": ["client_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_approval_reminder",
            "description": (
                "Drafts a copy-paste-ready reminder message addressed to a document's APPROVER (from "
                "get_sow_summary's document_responsibilities: {'owner': ..., 'approver': ...}) so the PM "
                "can copy it and send it themselves — nothing is sent automatically. IMPORTANT — only "
                "call this AFTER the PM has explicitly confirmed they want a reminder drafted (e.g. "
                "'yes', 'please', 'go ahead and draft it', 'generate it'). Do NOT call this the first "
                "time a PM asks 'whom should I reach out to get X approved' — that first question should "
                "be answered with get_sow_summary (just the approver's name), followed by an offer like "
                "'want me to draft a ready-to-copy reminder to send them?'. Only once the PM says yes to "
                "that offer do you call this tool. If the SOW doesn't name an approver for that document "
                "(even if it names an owner), found comes back false with a plain reason; NEVER invent a "
                "name or draft a reminder to someone the document doesn't actually name as the approver."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "client_name": {"type": "string", "description": "The client's name."},
                    "doc_type": {
                        "type": "string",
                        "description": "The document the PM needs approved/provided, as they phrased it, e.g. 'BRD' or 'HLD'.",
                    },
                },
                "required": ["client_name", "doc_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_document_content",
            "description": (
                "Answer a question using the ACTUAL TEXT inside a client's document — not its "
                "structured fields (that's get_sow_summary) and not the file itself (that's "
                "request_template/get_document_versions). Returns the passages whose meaning "
                "is closest to the question, pulled from the document's real content, for you to "
                "answer from — quote or paraphrase only what these passages actually say, never "
                "invent an answer if nothing relevant comes back. Use this for open-ended content "
                "questions a plain field lookup can't answer, e.g. 'what does the SOW say about "
                "termination', 'what does the BRD say about the acceptance criteria', 'is there "
                "anything across Acme's documents about data retention'. Searches across every "
                "embedded document type for the client unless doc_type narrows it to one. If a "
                "document was uploaded before it had a chance to be indexed, it may not have "
                "matches yet — if nothing comes back, say so plainly rather than assuming the "
                "document has no such content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "client_name": {"type": "string", "description": "The client's name."},
                    "query": {
                        "type": "string",
                        "description": "The question or topic to search the document's content for.",
                    },
                    "doc_type": {
                        "type": "string",
                        "description": "Restrict the search to one document type, e.g. 'SOW'. Omit to search across all of the client's embedded documents.",
                    },
                },
                "required": ["client_name", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_delete_client",
            "description": (
                "Look up a client and prepare to delete them. Deletion hides the client from everywhere "
                "(chat, dashboard, uploads, search) but is recoverable for a retention window before it's "
                "permanently purged — not instant/irreversible. This tool does NOT delete anything itself — "
                "it only looks up the client and returns their info so the PM can review it. The actual "
                "deletion only happens if the PM explicitly confirms in the UI. Never claim a client was "
                "deleted after calling this tool — only the UI confirmation can make that true. Use this "
                "when the PM asks to delete, remove, or get rid of a client."
            ),
            "parameters": {
                "type": "object",
                "properties": {"client_name": {"type": "string", "description": "The client's name."}},
                "required": ["client_name"],
            },
        },
    },
]


def dispatch_tool(
    rest: SupabaseRestClient,
    client_storage: StorageBackend,
    template_storage: StorageBackend,
    config: PhaseConfig,
    tool_name: str,
    tool_input: dict[str, Any],
) -> dict[str, Any]:
    if tool_name == "list_phases":
        return {
            "phases": [
                {"sequence": p.sequence, "name": p.name, "required_documents": list(p.required_documents)}
                for p in config.phases
            ]
        }

    if tool_name == "get_client_status":
        client_name = tool_input["client_name"]
        client = get_or_create_client(rest, client_storage, config, client_name)
        existing = existing_document_types(rest, client)
        not_applicable = not_applicable_document_types(rest, client)
        satisfied = existing | not_applicable
        status = []
        for phase in config.phases:
            missing = missing_documents(phase, satisfied)
            na_in_phase = [d for d in phase.required_documents if d in not_applicable and d not in existing]
            status.append(
                {
                    "phase": phase.name,
                    "sequence": phase.sequence,
                    "complete": len(missing) == 0,
                    "missing_documents": list(missing),
                    "not_applicable_documents": na_in_phase,
                }
            )
        return {"client_name": client["name"], "phases": status}

    if tool_name == "request_template":
        doc_type = tool_input["doc_type"]
        client_name = tool_input["client_name"]
        try:
            result = request_template(rest, client_storage, template_storage, config, doc_type, client_name)
            return {
                "allowed": True,
                "filename": result.filename,
                "download_url": f"/api/templates/{doc_type}/download?client_name={client_name}",
            }
        except GatingBlocked as e:
            return {
                "allowed": False,
                "reason": e.decision.reason,
                "blocking_phase": e.decision.blocking_phase,
                "missing_documents": list(e.decision.missing_documents),
            }
        except TemplateNotFound:
            return {"allowed": False, "reason": f"No master template is on file yet for '{doc_type}'."}
        except TemplateFileMissing as e:
            return {"allowed": False, "reason": str(e)}
        except ValueError as e:
            return {"allowed": False, "reason": str(e)}

    if tool_name == "get_document_versions":
        client_name = tool_input["client_name"]
        doc_type = tool_input["doc_type"]
        try:
            versions = list_document_versions(rest, client_name, doc_type)
        except ClientDocumentNotFound as e:
            return {"found": False, "reason": str(e)}
        return {
            "found": True,
            "client_name": client_name,
            "doc_type": doc_type,
            "versions": [
                {
                    "version_number": v.version_number,
                    "filename": v.filename,
                    "uploaded_by": v.uploaded_by,
                    "comment": v.comment,
                    "uploaded_at": v.uploaded_at,
                    "download_url": (
                        f"/api/clients/{client_name}/documents/{doc_type}/versions/{v.version_number}/download"
                    ),
                }
                for v in versions
            ],
        }

    if tool_name == "get_document_location":
        client_name = tool_input["client_name"]
        doc_type = tool_input["doc_type"]
        try:
            location = get_document_location(rest, client_name, doc_type)
        except ClientDocumentNotFound as e:
            return {"found": False, "reason": str(e)}
        return {
            "found": True,
            "client_name": location.client_name,
            "doc_type": location.doc_type,
            "folder_path": location.folder_path,
            "filename": location.filename,
        }

    if tool_name == "mark_document_not_applicable":
        client_name = tool_input["client_name"]
        doc_type = tool_input["doc_type"]
        reason = tool_input.get("reason")
        try:
            resolve_phase_for_document(config, doc_type)
        except ValueError as e:
            return {"ok": False, "reason": str(e)}
        client = get_or_create_client(rest, client_storage, config, client_name)
        mark_document_not_applicable(rest, client, doc_type, reason=reason)
        return {"ok": True, "client_name": client["name"], "doc_type": doc_type, "reason": reason}

    if tool_name == "unmark_document_not_applicable":
        client_name = tool_input["client_name"]
        doc_type = tool_input["doc_type"]
        try:
            resolve_phase_for_document(config, doc_type)
        except ValueError as e:
            return {"ok": False, "reason": str(e)}
        client = find_client(rest, client_name)
        if client is None:
            return {"ok": False, "reason": f"No client named {client_name!r}"}
        was_marked = unmark_document_not_applicable(rest, client, doc_type)
        return {"ok": True, "client_name": client["name"], "doc_type": doc_type, "was_marked": was_marked}

    if tool_name == "search_document_types":
        query = tool_input["query"]
        matches = find_document_types(config, query)
        return {
            "query": query,
            "count": len(matches),
            "matches": [{"doc_type": m.doc_type, "phase_name": m.phase_name} for m in matches],
        }

    if tool_name == "get_sow_summary":
        client_name = tool_input["client_name"]
        try:
            result = get_sow_summary(rest, client_storage, client_name)
        except SowExtractionFailed as e:
            return {"found": False, "reason": str(e)}
        return {
            "found": True,
            "client_name": result.client_name,
            "contract_value": result.contract_value,
            "start_date": result.start_date,
            "end_date": result.end_date,
            "scope_summary": result.scope_summary,
            "team_assignments": result.team_assignments,
            "document_responsibilities": result.document_responsibilities,
            "extracted_at": result.extracted_at,
        }

    if tool_name == "generate_approval_reminder":
        client_name = tool_input["client_name"]
        doc_type = tool_input["doc_type"]
        try:
            result = generate_approval_reminder(rest, client_storage, client_name, doc_type)
        except SowExtractionFailed as e:
            return {"found": False, "reason": str(e)}
        if not result.found:
            return {"found": False, "client_name": result.client_name, "doc_type": doc_type, "reason": result.reason}
        return {
            "found": True,
            "client_name": result.client_name,
            "doc_type": result.matched_doc_type,
            "owner": result.owner,
            "approver": result.approver,
            "reminder_message": result.reminder_message,
        }

    if tool_name == "search_document_content":
        client_name = tool_input["client_name"]
        query = tool_input["query"]
        doc_type = tool_input.get("doc_type")
        client = find_client(rest, client_name)
        if client is None:
            return {"found": False, "reason": f"No client named {client_name!r}"}
        matches = embedding_service.search_document_content(rest, client["id"], query, doc_type=doc_type)
        return {
            "found": len(matches) > 0,
            "client_name": client["name"],
            "query": query,
            "matches": [
                {
                    "doc_type": m.doc_type,
                    "version_number": m.version_number,
                    "content": m.content,
                    "similarity": m.similarity,
                }
                for m in matches
            ],
        }

    if tool_name == "propose_delete_client":
        client_name = tool_input["client_name"]
        client = find_client(rest, client_name)
        if client is None:
            return {"found": False, "client_name": client_name}

        existing = existing_document_types(rest, client)
        satisfied = satisfied_document_types(rest, client)
        phases_complete = sum(1 for phase in config.phases if not missing_documents(phase, satisfied))
        return {
            "found": True,
            "needs_confirmation": True,
            "client_name": client["name"],
            "phases_complete": phases_complete,
            "total_phases": len(config.phases),
            "document_count": len(existing),
        }

    raise ValueError(f"Unknown tool: {tool_name}")
