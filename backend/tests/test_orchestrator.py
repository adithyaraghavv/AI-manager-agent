from unittest.mock import MagicMock, patch

import httpx
from groq import BadRequestError

from app.agent.orchestrator import run_turn


def _bad_request_error(code: str) -> BadRequestError:
    request = httpx.Request("POST", "https://api.groq.com/x")
    response = httpx.Response(400, request=request)
    return BadRequestError(code, response=response, body={"error": {"code": code, "message": "x"}})


def _plain_text_response(text: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = text
    choice.message.tool_calls = None
    response = MagicMock()
    response.choices = [choice]
    return response


def test_tool_use_failed_retries_without_tools_instead_of_crashing():
    # Reproduces a live failure: Groq/Llama occasionally emits a malformed tool call
    # and rejects it with a 400 tool_use_failed error. This must degrade to a plain-text
    # reply, never propagate as an unhandled crash (previously surfaced as a 500 to the PM).
    err = _bad_request_error("tool_use_failed")
    fallback = _plain_text_response("Sorry, could you rephrase?")

    with patch("app.agent.orchestrator.Groq") as MockGroq:
        instance = MockGroq.return_value
        instance.chat.completions.create.side_effect = [err, fallback]

        messages = [{"role": "user", "content": "yes"}]
        result = run_turn(None, None, None, None, messages)

    assert result[-1] == {"role": "assistant", "content": "Sorry, could you rephrase?"}
    assert instance.chat.completions.create.call_count == 2


def test_other_bad_request_errors_are_not_swallowed():
    # Only tool_use_failed should be caught and retried — any other 400 (e.g. bad API key,
    # malformed request) should propagate normally rather than being silently masked.
    err = _bad_request_error("invalid_api_key")

    with patch("app.agent.orchestrator.Groq") as MockGroq:
        instance = MockGroq.return_value
        instance.chat.completions.create.side_effect = [err]

        messages = [{"role": "user", "content": "hi"}]
        try:
            run_turn(None, None, None, None, messages)
            assert False, "expected BadRequestError to propagate"
        except BadRequestError:
            pass
