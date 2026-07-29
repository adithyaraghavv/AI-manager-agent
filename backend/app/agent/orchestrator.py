from typing import Any

import anthropic
from sqlalchemy.orm import Session

from app.agent.tools import TOOL_DEFINITIONS, dispatch_tool
from app.config import settings
from app.core.phase_config import PhaseConfig
from app.storage.base import StorageBackend

SYSTEM_PROMPT = """You are the Marlabs Delivery Assistant, a conversational agent that helps \
project managers navigate the standard project document lifecycle (7 phases, from \
Pre-requisites through Maintenance).

Rules:
- Always check a client's status before claiming a document is or isn't available.
- Phase-gating is a HARD BLOCK you must respect and explain, never override or argue around it.
- If a template request is blocked, tell the PM exactly which documents are missing and offer to \
help them get those first.
- Be concise and practical. This is a working tool for busy PMs, not a chatty assistant."""

MODEL = "claude-sonnet-5"


def run_turn(
    db: Session,
    client_storage: StorageBackend,
    template_storage: StorageBackend,
    config: PhaseConfig,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run one assistant turn (including any tool-call round trips) and
    return the updated message list with the assistant's reply appended."""
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        content_blocks = [block.model_dump() for block in response.content]
        messages.append({"role": "assistant", "content": content_blocks})

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = dispatch_tool(db, client_storage, template_storage, config, block.name, block.input)
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": str(result)}
            )
        messages.append({"role": "user", "content": tool_results})

    return messages
