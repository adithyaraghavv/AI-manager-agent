from unittest.mock import MagicMock, patch

import httpx
from groq import BadRequestError

from app.agent.orchestrator import FALLBACK_REPLY, run_turn


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


def test_tool_use_failed_retries_with_tools_before_giving_up():
    # Reproduces a live failure: Groq/Llama occasionally emits a malformed tool call and
    # rejects it with a 400 tool_use_failed error. A single failure is usually transient, so
    # the retry should still have tools enabled — giving the PM a real answer, not just an
    # apology — rather than immediately falling back to a canned message.
    err = _bad_request_error("tool_use_failed")
    real_answer = _plain_text_response("Hillenbrand is missing MSA, SOW, Pricing.")

    with patch("app.agent.orchestrator.Groq") as MockGroq:
        instance = MockGroq.return_value
        instance.chat.completions.create.side_effect = [err, real_answer]

        messages = [{"role": "user", "content": "what's the status for Hillenbrand?"}]
        result = run_turn(None, None, None, None, messages)

    assert result[-1] == {"role": "assistant", "content": "Hillenbrand is missing MSA, SOW, Pricing."}
    assert instance.chat.completions.create.call_count == 2


def test_tool_use_failed_twice_falls_back_to_canned_reply_not_model_text():
    # If the retry also fails, give up on tools for this turn rather than looping forever.
    # Critically: don't trust the model's own explanation here — observed live that when
    # suddenly told to answer without tools mid-failure, it invents confused text (e.g.
    # offering to "simulate" data) instead of a clean answer. Always show our own message.
    err1 = _bad_request_error("tool_use_failed")
    err2 = _bad_request_error("tool_use_failed")

    with patch("app.agent.orchestrator.Groq") as MockGroq:
        instance = MockGroq.return_value
        instance.chat.completions.create.side_effect = [err1, err2]

        messages = [{"role": "user", "content": "what's the status for Hillenbrand?"}]
        result = run_turn(None, None, None, None, messages)

    assert result[-1] == {"role": "assistant", "content": FALLBACK_REPLY}
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
