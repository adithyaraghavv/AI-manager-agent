"""Tool definitions for the conversational layer (OpenAI-style function-calling
schema, used by the Groq API).

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

from sqlalchemy.orm import Session

from app.core.gating import missing_documents
from app.core.phase_config import PhaseConfig
from app.services.client_service import existing_document_types, get_or_create_client
from app.services.document_service import GatingBlocked, TemplateNotFound, request_template
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
]


def dispatch_tool(
    db: Session,
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
        client = get_or_create_client(db, client_storage, config, client_name)
        existing = existing_document_types(db, client)
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
        return {"client_name": client_name, "phases": status}

    if tool_name == "request_template":
        doc_type = tool_input["doc_type"]
        client_name = tool_input["client_name"]
        try:
            result = request_template(db, client_storage, template_storage, config, doc_type, client_name)
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
        except ValueError as e:
            return {"allowed": False, "reason": str(e)}

    raise ValueError(f"Unknown tool: {tool_name}")
