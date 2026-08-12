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
from app.core.gating import missing_documents
from app.core.phase_config import PhaseConfig
from app.db.rest_client import SupabaseRestClient
from app.services.client_service import existing_document_types, find_client, get_or_create_client
from app.services.document_service import (
    ClientDocumentNotFound,
    GatingBlocked,
    TemplateFileMissing,
    TemplateNotFound,
    list_document_versions,
    request_template,
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
                "an earlier version; every upload is kept permanently. Use this when the PM asks about "
                "version history, a document's past versions, or wants to see/download an older version."
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
        status = []
        for phase in config.phases:
            missing = missing_documents(phase, existing)
            status.append(
                {
                    "phase": phase.name,
                    "sequence": phase.sequence,
                    "complete": len(missing) == 0,
                    "missing_documents": list(missing),
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

    if tool_name == "search_document_types":
        query = tool_input["query"]
        matches = find_document_types(config, query)
        return {
            "query": query,
            "count": len(matches),
            "matches": [{"doc_type": m.doc_type, "phase_name": m.phase_name} for m in matches],
        }

    if tool_name == "propose_delete_client":
        client_name = tool_input["client_name"]
        client = find_client(rest, client_name)
        if client is None:
            return {"found": False, "client_name": client_name}

        existing = existing_document_types(rest, client)
        phases_complete = sum(1 for phase in config.phases if not missing_documents(phase, existing))
        return {
            "found": True,
            "needs_confirmation": True,
            "client_name": client["name"],
            "phases_complete": phases_complete,
            "total_phases": len(config.phases),
            "document_count": len(existing),
        }

    raise ValueError(f"Unknown tool: {tool_name}")
