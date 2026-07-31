import json
from typing import Any

from groq import BadRequestError, Groq

from app.agent.tools import TOOL_DEFINITIONS, dispatch_tool
from app.config import settings
from app.core.phase_config import PhaseConfig
from app.db.rest_client import SupabaseRestClient
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
- get_client_status tells you which documents haven't been FILED yet for each phase — that is \
NOT the same as whether a template can be REQUESTED. Only request_template's "allowed" field \
decides that. A phase-1 document's template is always requestable (phase 1 has no prerequisite), \
even if get_client_status shows phase-1 documents as missing/not-yet-filed. Never contradict what \
request_template just told you — if it says allowed=true, confirm the template is ready. The UI \
already renders a clickable download button for it — do NOT paste the raw download_url path in \
your reply, that's redundant and looks unpolished; just say something like "The Pricing template \
is ready — you can download it above."
- Phase-gating is a HARD BLOCK you must respect and explain, never override or argue around it.
- If a template request is blocked, tell the PM exactly which documents are missing and offer to \
help them get those first.
- Be concise and practical. This is a working tool for busy PMs, not a chatty assistant."""

MODEL = "llama-3.3-70b-versatile"
MAX_TOOL_ROUNDS = 6
FALLBACK_REPLY = (
    "Sorry, I had trouble processing that. Could you rephrase, or tell me the client name "
    "and document type you're asking about directly?"
)


def _is_tool_use_failed(error: BadRequestError) -> bool:
    body = error.body
    return isinstance(body, dict) and body.get("error", {}).get("code") == "tool_use_failed"


def run_turn(
    rest: SupabaseRestClient,
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
        try:
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=1024,
                tools=TOOL_DEFINITIONS,
                tool_choice="auto",
                messages=api_messages,
            )
        except BadRequestError as e:
            # Llama on Groq occasionally emits a malformed tool-call (e.g. "<function=..."
            # instead of proper JSON) and Groq rejects it with tool_use_failed. Rather than
            # surfacing that as a crash, retry once with tools disabled so the model is forced
            # to just answer in plain text — degraded, but never a dead end for the PM.
            if not _is_tool_use_failed(e):
                raise
            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=1024,
                tool_choice="none",
                messages=api_messages,
            )
            choice = response.choices[0].message
            assistant_message = {"role": "assistant", "content": choice.content or FALLBACK_REPLY}
            messages.append(assistant_message)
            return messages

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
            result = dispatch_tool(rest, client_storage, template_storage, config, tc.function.name, tool_input)
            tool_message = {
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tc.function.name,
                "content": json.dumps(result),
            }
            messages.append(tool_message)
            api_messages.append(tool_message)

    return messages
