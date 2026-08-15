from unittest.mock import MagicMock, patch

import httpx
from openai import BadRequestError

from app.agent.orchestrator import SYSTEM_PROMPT, run_turn


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


def test_system_prompt_forbids_fabricating_download_links():
    # Regression guard for a real bug seen live: asked for a download link,
    # the model invented plausible-looking but fake URLs (e.g.
    # "sandbox:/api/...") instead of calling get_document_versions and using
    # its real download_url. Every link must come from an actual tool result.
    assert "NEVER invent, construct, guess, or reconstruct a download URL" in SYSTEM_PROMPT


def test_system_prompt_requires_exact_document_type_names():
    # Regression guard for a real bug seen live: "signed off test summary
    # report" (the PM's casual phrasing) didn't match the config's exact
    # "Signed-off Test Summary Report" and got rejected as undefined, even
    # though the document type does exist.
    assert "must match EXACTLY as they appear in list_phases" in SYSTEM_PROMPT


def test_system_prompt_requires_disambiguation_for_loose_document_names():
    # Guided document discovery: a PM who doesn't know the exact document
    # name (e.g. just says "the test document") should get a clarifying
    # question listing every real match, not a guess.
    assert "call search_document_types with their" in SYSTEM_PROMPT
    assert "never pick one for them" in SYSTEM_PROMPT


def test_system_prompt_does_not_default_to_version_history_for_plain_requests():
    # Regression guard for a real bug seen live: "give me SOW" for a client
    # with zero uploaded SOWs incorrectly called get_document_versions
    # (found none, told the PM to go upload one) instead of request_template
    # (which would have handed over the master template to fill in). Adding
    # search_document_types confused which tool comes next after resolving
    # an ambiguous name.
    assert "search_document_types ONLY resolves which exact document type" in SYSTEM_PROMPT
    assert "means request_template" in SYSTEM_PROMPT
    assert "Do not default to get_document_versions" in SYSTEM_PROMPT


def test_system_prompt_distinguishes_path_only_requests_from_document_requests():
    # get_document_location must only be used for an explicit "where is it
    # stored" question, never substituted for a plain "give me X" request.
    assert "get_document_location is a DIFFERENT thing from requesting a document" in SYSTEM_PROMPT


def test_system_prompt_forbids_answering_from_stale_conversation_history():
    # Regression guard for a real bug seen live: within one conversation, the model
    # reused an earlier tool result (e.g. "template file missing") for a repeated
    # request instead of calling the tool again — even after the underlying state
    # had actually changed (the file got seeded). Tool results must never be
    # treated as still valid just because they're in the conversation history.
    assert "ALWAYS call the tool again for every new request" in SYSTEM_PROMPT
    assert "never guaranteed to still be accurate" in SYSTEM_PROMPT


def test_system_prompt_asks_for_a_warm_natural_tone_not_a_terse_bot():
    # Feedback from a live demo: responses read as stiff/robotic, not like a
    # natural assistant (Claude/ChatGPT-style). The old prompt explicitly said
    # "not a chatty assistant" with no positive guidance toward warmth — that's
    # what produced the clipped tone. Guard against that instruction sneaking
    # back in without a corresponding push toward natural, varied phrasing.
    assert "not a scripted bot" in SYSTEM_PROMPT
    assert "not a chatty assistant" not in SYSTEM_PROMPT


def test_system_prompt_distinguishes_not_applicable_from_missing_in_status():
    assert "get_client_status's missing_documents excludes anything marked not-applicable" in SYSTEM_PROMPT


def test_system_prompt_forbids_using_not_applicable_as_a_gate_workaround():
    # The exact failure mode this guards against: an agent marking a blocked
    # document not-applicable just to unblock a phase the PM actually wants,
    # silently defeating the hard gate instead of respecting it.
    assert "NEVER call it just because a request got blocked" in SYSTEM_PROMPT
    assert "that would silently defeat the hard gate" in SYSTEM_PROMPT


def test_system_prompt_self_corrects_on_unrecognized_doc_type_for_mark_unmark():
    # Live bug: unmark_document_not_applicable failed on a mismatched doc_type
    # string and the assistant just relayed the failure instead of resolving
    # the exact name and retrying, which read to the PM as "this was never
    # marked" when it actually had been.
    assert "don't just relay that as failure" in SYSTEM_PROMPT
    assert "call search_document_types with the PM's phrase to resolve the" in SYSTEM_PROMPT


def test_system_prompt_distinguishes_sow_content_questions_from_file_requests():
    # get_sow_summary answers questions ABOUT the SOW (value, dates, scope);
    # a plain "give me the SOW" must still mean the file itself.
    assert "get_sow_summary is ALSO different from requesting the SOW file" in SYSTEM_PROMPT
    assert "never fill in a guess" in SYSTEM_PROMPT


def test_system_prompt_general_sow_summary_request_surfaces_all_six_fields():
    # A plain "summarize the SOW" must not silently reduce to just one field
    # (what happened live before) — the PM asking generally wants the whole
    # picture: value, both dates, scope, team, and document ownership.
    assert "present ALL SIX fields together" in SYSTEM_PROMPT
    assert "not just whichever one you'd otherwise guess at" in SYSTEM_PROMPT


def test_system_prompt_forbids_silently_dropping_null_team_or_ownership_from_the_reply():
    # Live bug: the tool-result card correctly showed "doesn't spell out a
    # project team or document ownership," but the assistant's own written
    # reply just went quiet on those two fields instead of saying so itself —
    # reads as an incomplete, templated answer rather than a real summary.
    assert "your own written reply must explicitly cover team assignments and document responsibilities every time" in SYSTEM_PROMPT
    assert "is incomplete, not concise" in SYSTEM_PROMPT


def test_system_prompt_forbids_inventing_team_or_document_ownership():
    # Demo feedback: PMs want to ask who's on the project team and who owns
    # providing each document. Both are exactly the kind of thing the model
    # could plausibly guess wrong (a name, a role, "who usually owns this") —
    # guard against fabrication here as strictly as any other SOW field.
    assert "team_assignments and document_responsibilities are exactly as fabrication-sensitive" in SYSTEM_PROMPT
    assert "never infer one from context" in SYSTEM_PROMPT


def test_system_prompt_distinguishes_reminder_generation_from_plain_ownership_question():
    # generate_approval_reminder is for "who do I reach out to" intent
    # (drafts a message); get_sow_summary is for a plain "who's responsible"
    # fact question. Both must still refuse to invent a name for a document
    # the SOW doesn't actually assign.
    assert 'generate_approval_reminder is for "whom should I reach out to' in SYSTEM_PROMPT
    assert "do NOT invent a name or a plausible role to draft a reminder to" in SYSTEM_PROMPT


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
