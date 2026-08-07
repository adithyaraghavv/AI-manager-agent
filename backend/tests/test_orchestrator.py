from unittest.mock import MagicMock, patch

import httpx
from openai import BadRequestError

from app.agent.orchestrator import run_turn


def _bad_request_error(code: str) -> BadRequestError:
    request = httpx.Request("POST", "https://api.openai.com/x")
    response = httpx.Response(400, request=request)
    return BadRequestError(code, response=response, body={"error": {"code": code, "message": "x"}})


def _plain_text_response(text: str) -> MagicMock:
    choice = MagicMock()
    choice.message.content = text
    choice.message.tool_calls = None
    response = MagicMock()
    response.choices = [choice]
    return response


def test_plain_reply_with_no_tool_calls_is_appended_to_messages():
    response = _plain_text_response("Hillenbrand is missing MSA, SOW, Pricing.")

    with patch("app.agent.orchestrator.OpenAI") as MockOpenAI:
        instance = MockOpenAI.return_value
        instance.chat.completions.create.return_value = response

        messages = [{"role": "user", "content": "what's the status for Hillenbrand?"}]
        result = run_turn(None, None, None, None, messages)

    assert result[-1] == {"role": "assistant", "content": "Hillenbrand is missing MSA, SOW, Pricing."}
    assert instance.chat.completions.create.call_count == 1


def test_bad_request_errors_are_not_swallowed():
    # A 400 (e.g. bad API key, malformed request) should propagate normally
    # rather than being silently masked.
    err = _bad_request_error("invalid_api_key")

    with patch("app.agent.orchestrator.OpenAI") as MockOpenAI:
        instance = MockOpenAI.return_value
        instance.chat.completions.create.side_effect = [err]

        messages = [{"role": "user", "content": "hi"}]
        try:
            run_turn(None, None, None, None, messages)
            assert False, "expected BadRequestError to propagate"
        except BadRequestError:
            pass
