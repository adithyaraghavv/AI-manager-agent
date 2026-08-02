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


def test_select_raises_on_http_error():
    client = _client_with_transport(lambda request: httpx.Response(401, json={"message": "unauthorized"}))
    try:
        client.select("clients", name="Acme")
        assert False, "expected HTTPStatusError"
    except httpx.HTTPStatusError:
        pass
