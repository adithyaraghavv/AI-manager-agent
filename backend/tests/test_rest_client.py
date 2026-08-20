import httpx

from app.db.rest_client import SupabaseRestClient


def _client_with_transport(handler) -> SupabaseRestClient:
    client = SupabaseRestClient("https://example.supabase.co", "test-key")
    client._client = httpx.Client(
        base_url=client._client.base_url,
        headers=client._client.headers,
        transport=httpx.MockTransport(handler),
    )
    return client


def test_select_builds_postgrest_eq_filters():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=[{"id": 1, "name": "Acme"}])

    client = _client_with_transport(handler)
    rows = client.select("clients", name="Acme", id=1)

    assert rows == [{"id": 1, "name": "Acme"}]
    assert "name=eq.Acme" in captured["url"]
    assert "id=eq.1" in captured["url"]
    assert captured["headers"]["apikey"] == "test-key"
    assert captured["headers"]["authorization"] == "Bearer test-key"


def test_select_one_returns_none_when_empty():
    client = _client_with_transport(lambda request: httpx.Response(200, json=[]))
    assert client.select_one("clients", name="Nobody") is None


def test_insert_sends_prefer_representation_header_and_returns_first_row():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["prefer"] = request.headers.get("prefer")
        captured["body"] = request.content
        return httpx.Response(201, json=[{"id": 5, "name": "NewClient"}])

    client = _client_with_transport(handler)
    row = client.insert("clients", {"name": "NewClient"})

    assert row == {"id": 5, "name": "NewClient"}
    assert captured["method"] == "POST"
    assert captured["prefer"] == "return=representation"


def test_update_filters_by_match_and_returns_first_row():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        return httpx.Response(200, json=[{"id": 5, "filename": "new.pdf"}])

    client = _client_with_transport(handler)
    row = client.update("client_documents", {"id": 5}, {"filename": "new.pdf"})

    assert row == {"id": 5, "filename": "new.pdf"}
    assert captured["method"] == "PATCH"
    assert "id=eq.5" in captured["url"]


def test_select_one_ci_uses_ilike_for_case_insensitive_match():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[{"id": 1, "name": "Hillenbrand"}])

    client = _client_with_transport(handler)
    row = client.select_one_ci("clients", "name", "hillenbrand")

    assert row == {"id": 1, "name": "Hillenbrand"}
    assert "name=ilike.hillenbrand" in captured["url"]


def test_select_one_ci_escapes_wildcard_characters():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["value"] = request.url.params["name"]
        return httpx.Response(200, json=[])

    client = _client_with_transport(handler)
    client.select_one_ci("clients", "name", "100%_Corp")

    # Raw % and _ would otherwise act as SQL LIKE wildcards, turning an exact
    # lookup into an accidental pattern search — must be escaped.
    assert captured["value"] == "ilike.100\\%\\_Corp"


def test_select_one_ci_returns_none_when_no_match():
    client = _client_with_transport(lambda request: httpx.Response(200, json=[]))
    assert client.select_one_ci("clients", "name", "Nobody") is None


def test_delete_sends_delete_method_with_eq_filters():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        return httpx.Response(204)

    client = _client_with_transport(handler)
    client.delete("client_documents", client_id=5)

    assert captured["method"] == "DELETE"
    assert "client_id=eq.5" in captured["url"]


def test_select_ilike_any_queries_each_column_separately_not_via_or_syntax():
    # Regression test: an earlier version built a hand-rolled PostgREST
    # `or=(...)` filter, which treats commas/parens as structural — a search
    # term containing either could inject extra conditions and widen the
    # query far beyond a genuine substring match. Per-column requests avoid
    # that mini-language entirely, so no request should ever carry an `or=`
    # param, regardless of what characters are in the search term.
    captured_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, json=[])

    client = _client_with_transport(handler)
    client.select_ilike_any("client_documents", ["filename", "doc_type"], "x),deleted_at.is.null,(y")

    assert len(captured_urls) == 2  # one request per column
    for url in captured_urls:
        assert "or=" not in url


def test_select_ilike_any_merges_and_dedupes_results_across_columns():
    def handler(request: httpx.Request) -> httpx.Response:
        if "filename" in str(request.url):
            return httpx.Response(200, json=[{"id": 1, "filename": "MSA.pdf"}, {"id": 2, "filename": "MSA_2.pdf"}])
        return httpx.Response(200, json=[{"id": 2, "doc_type": "MSA"}])  # id=2 matches both columns

    client = _client_with_transport(handler)
    rows = client.select_ilike_any("client_documents", ["filename", "doc_type"], "MSA")

    assert [r["id"] for r in rows] == [1, 2]  # id=2 only appears once, not twice


def test_select_raises_on_http_error():
    client = _client_with_transport(lambda request: httpx.Response(401, json={"message": "unauthorized"}))
    try:
        client.select("clients", name="Acme")
        assert False, "expected HTTPStatusError"
    except httpx.HTTPStatusError:
        pass


def test_select_in_with_empty_values_makes_zero_http_calls():
    # The whole point of the short-circuit — callers that pass an empty list
    # (e.g. "look up parents for these 0 children") shouldn't pay a network
    # round-trip to learn what they already know.
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=[])

    client = _client_with_transport(handler)
    result = client.select_in("clients", "id", [])

    assert result == []
    assert call_count == 0


def test_select_in_batches_ids_into_single_request():
    captured_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, json=[{"id": 1}, {"id": 2}, {"id": 3}])

    client = _client_with_transport(handler)
    rows = client.select_in("clients", "id", [1, 2, 3])

    assert rows == [{"id": 1}, {"id": 2}, {"id": 3}]
    assert len(captured_urls) == 1  # one round-trip, not three
    # httpx URL-encodes commas and parens in the query string; either
    # encoded or raw form is fine, both are valid PostgREST.
    assert "id=in.%281%2C2%2C3%29" in captured_urls[0] or "id=in.(1,2,3)" in captured_urls[0]


def test_select_in_escapes_string_values_containing_commas():
    # PostgREST's in.(...) list is comma-separated, so a raw comma inside a
    # value would be parsed as a value boundary. Wrap in double quotes and
    # escape inner quotes/backslashes.
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["column_value"] = request.url.params["name"]
        return httpx.Response(200, json=[])

    client = _client_with_transport(handler)
    client.select_in("clients", "name", ["Acme", "Foo, Inc.", 'Weird"Co'])

    v = captured["column_value"]
    assert v.startswith("in.(") and v.endswith(")")
    inside = v[len("in.") + 1 : -1]
    # "Acme" has no structural chars → stays bare; the other two get quoted.
    assert inside == 'Acme,"Foo, Inc.","Weird\\"Co"'


def test_select_in_chunks_large_value_lists_into_multiple_requests():
    # 700 values > 500 chunk size → 2 requests (500 + 200). Keeps a single
    # ?col=in.(...) filter under typical proxy URL-length limits.
    captured_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, json=[{"id": 1}])

    client = _client_with_transport(handler)
    rows = client.select_in("clients", "id", list(range(1, 701)))

    assert len(captured_urls) == 2
    assert len(rows) == 2  # one row per chunk from our fake handler


def test_insert_many_with_empty_rows_makes_zero_http_calls():
    # Callers that build a batch and discover it's empty (e.g. "no chunks
    # extracted from this doc") shouldn't pay a network round-trip.
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=[])

    client = _client_with_transport(handler)
    result = client.insert_many("document_chunks", [])

    assert result == []
    assert call_count == 0


def test_insert_many_sends_all_rows_in_single_request_as_json_array():
    # The whole point: N rows → 1 POST, not N POSTs. Body is a JSON array
    # (that's how PostgREST distinguishes bulk from single-row inserts).
    import json

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.setdefault("calls", 0)
        captured["calls"] += 1
        captured["method"] = request.method
        captured["prefer"] = request.headers.get("prefer")
        captured["body"] = json.loads(request.content)
        # PostgREST returns one row per input row with server-assigned ids.
        return httpx.Response(
            201,
            json=[{"id": i + 1, **row} for i, row in enumerate(captured["body"])],
        )

    client = _client_with_transport(handler)
    rows = client.insert_many(
        "document_chunks",
        [
            {"chunk_index": 0, "content": "a"},
            {"chunk_index": 1, "content": "b"},
            {"chunk_index": 2, "content": "c"},
        ],
    )

    assert captured["calls"] == 1  # one round-trip, not three
    assert captured["method"] == "POST"
    assert captured["prefer"] == "return=representation"
    assert isinstance(captured["body"], list) and len(captured["body"]) == 3
    assert [r["chunk_index"] for r in rows] == [0, 1, 2]
    assert all("id" in r for r in rows)


def test_insert_many_chunks_large_batches_into_multiple_requests():
    # 1500 rows > 500 chunk size → 3 requests (500 + 500 + 500). Keeps each
    # POST body under PostgREST's default 1 MiB request cap. Returned list
    # concatenates every chunk in insertion order.
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        import json
        body = json.loads(request.content)
        return httpx.Response(201, json=[{"id": i, **row} for i, row in enumerate(body)])

    client = _client_with_transport(handler)
    rows = client.insert_many(
        "document_chunks",
        [{"chunk_index": i} for i in range(1500)],
    )

    assert call_count == 3
    assert len(rows) == 1500
