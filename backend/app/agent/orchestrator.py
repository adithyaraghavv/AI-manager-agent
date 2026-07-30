import json
from typing import Any

from groq import Groq
from sqlalchemy.orm import Session

from app.agent.tools import TOOL_DEFINITIONS, dispatch_tool
from app.config import settings
from app.core.phase_config import PhaseConfig
from app.storage.base import StorageBackend

SYSTEM_PROMPT = """You are the Marlabs Delivery Assistant, a conversational agent that helps \
project managers navigate the standard project document lifecycle (7 phases, from \
Pre-requisites through Maintenance).

Rules:
- Only use a tool when the PM's message actually requires one — a specific document/template \
request, a status check, or an explicit question about phases/requirements.
- For a greeting or small talk (e.g. "hi", "hello", "thanks"), just reply naturally and briefly \
ask how you can help. Do NOT call list_phases or any other tool for this — wait until the PM \
asks something that needs one.
- Always check a client's status before claiming a document is or isn't available.
- Phase-gating is a HARD BLOCK you must respect and explain, never override or argue around it.
- If a template request is blocked, tell the PM exactly which documents are missing and offer to \
help them get those first.
- Be concise and practical. This is a working tool for busy PMs, not a chatty assistant."""

MODEL = "llama-3.3-70b-versatile"
MAX_TOOL_ROUNDS = 6


def run_turn(
    db: Session,
    client_storage: StorageBackend,
    template_storage: StorageBackend,
    config: PhaseConfig,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run one assistant turn (including any tool-call round trips) and
    return the updated message list with the assistant's reply appended."""
    client = Groq(api_key=settings.groq_api_key)

    api_messages = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=1024,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            messages=api_messages,
        )
        choice = response.choices[0].message

        assistant_message: dict[str, Any] = {"role": "assistant", "content": choice.content or ""}
        if choice.tool_calls:
            assistant_message["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in choice.tool_calls
            ]
        messages.append(assistant_message)
        api_messages.append(assistant_message)

        if not choice.tool_calls:
            break

        for tc in choice.tool_calls:
            tool_input = json.loads(tc.function.arguments or "{}")
            result = dispatch_tool(db, client_storage, template_storage, config, tc.function.name, tool_input)
            tool_message = {
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.function.name,
                "content": json.dumps(result),
            }
            messages.append(tool_message)
            api_messages.append(tool_message)

    return messages
