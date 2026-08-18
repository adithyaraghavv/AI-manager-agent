from unittest.mock import MagicMock, patch

import pytest

from app.core.phase_config import Phase, PhaseConfig
from app.services import embedding_service
from app.services.document_service import upload_document
from app.services.embedding_service import chunk_text, embed_document, search_document_content
from app.storage.local import LocalFilesystemStorage

CONFIG = PhaseConfig(
    [
        Phase(name="Pre-requisites", sequence=1, required_documents=("MSA", "SOW")),
    ]
)


@pytest.fixture
def storage(tmp_path):
    return LocalFilesystemStorage(tmp_path)


def _mock_embeddings_response(vectors: list[list[float]]) -> MagicMock:
    response = MagicMock()
    response.data = [MagicMock(embedding=v) for v in vectors]
    return response


# ---- chunk_text ----

def test_chunk_text_splits_long_text_into_overlapping_pieces():
    text = "a" * 1000
    chunks = chunk_text(text, chunk_size=400, overlap=50)

    assert len(chunks) > 1
    # Every chunk after the first starts inside the previous chunk's tail —
    # that's what "overlap" means, and it's what keeps a sentence spanning a
    # boundary readable from at least one chunk.
    assert text[350:400] in chunks[0]


def test_chunk_text_short_text_is_a_single_chunk():
    assert chunk_text("just one short sentence.") == ["just one short sentence."]


def test_chunk_text_empty_or_whitespace_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


# ---- embed_document ----

def test_embed_document_works_for_any_doc_type_not_just_sow(rest):
    # Stage 2: no doc_type allowlist — BRD, HLD, LLD etc. all get embedded
    # the same way SOW does, as long as their text can be extracted.
    with patch("app.services.embedding_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.embeddings.create.return_value = _mock_embeddings_response([[1.0, 0.0]])
        count = embed_document(rest, client_id=1, doc_type="BRD", version_number=1, content=b"brd text", extension="txt")

    assert count == 1
    rows = rest.select("document_chunks", client_id=1, doc_type="BRD", version_number=1)
    assert len(rows) == 1


def test_embed_document_skips_unreadable_content(rest):
    # .bin isn't a supported extraction format — extract_text returns None.
    count = embed_document(rest, client_id=1, doc_type="SOW", version_number=1, content=b"\x00\x01", extension="bin")

    assert count == 0
    assert rest.select("document_chunks") == []


def test_embed_document_stores_one_row_per_chunk(rest):
    text = ("This SOW covers project scope and deliverables. " * 40).strip()

    with patch("app.services.embedding_service.OpenAI") as MockOpenAI:
        pieces = chunk_text(text)
        MockOpenAI.return_value.embeddings.create.return_value = _mock_embeddings_response(
            [[float(i)] * 3 for i in range(len(pieces))]
        )
        count = embed_document(rest, client_id=1, doc_type="SOW", version_number=1, content=text.encode(), extension="txt")

    assert count == len(pieces)
    rows = rest.select("document_chunks", client_id=1, doc_type="SOW", version_number=1)
    assert len(rows) == len(pieces)
    assert {r["chunk_index"] for r in rows} == set(range(len(pieces)))


def test_embed_document_replaces_prior_chunks_for_same_version(rest):
    with patch("app.services.embedding_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.embeddings.create.return_value = _mock_embeddings_response([[1.0, 0.0]])
        embed_document(rest, client_id=1, doc_type="SOW", version_number=1, content=b"first upload text", extension="txt")

        MockOpenAI.return_value.embeddings.create.return_value = _mock_embeddings_response([[0.0, 1.0]])
        embed_document(rest, client_id=1, doc_type="SOW", version_number=1, content=b"replacement text", extension="txt")

    rows = rest.select("document_chunks", client_id=1, doc_type="SOW", version_number=1)
    # Still just the chunks from the SECOND call — the first call's row was
    # replaced, not left behind as a stale duplicate.
    assert len(rows) == 1
    assert rows[0]["content"] == "replacement text"


def test_embed_document_returns_zero_on_embedding_api_failure(rest):
    # An upload must never fail just because the embedding call did —
    # this is a bonus feature layered on top of a real upload.
    with patch("app.services.embedding_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.embeddings.create.side_effect = RuntimeError("network error")
        count = embed_document(rest, client_id=1, doc_type="SOW", version_number=1, content=b"some sow text", extension="txt")

    assert count == 0
    assert rest.select("document_chunks") == []


# ---- search_document_content ----

def test_search_document_content_ranks_by_similarity(rest):
    rest.insert(
        "document_chunks",
        {"client_id": 1, "doc_type": "SOW", "version_number": 1, "chunk_index": 0,
         "content": "termination clause text", "embedding": [1.0, 0.0, 0.0]},
    )
    rest.insert(
        "document_chunks",
        {"client_id": 1, "doc_type": "SOW", "version_number": 1, "chunk_index": 1,
         "content": "unrelated pricing text", "embedding": [0.0, 1.0, 0.0]},
    )

    with patch("app.services.embedding_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.embeddings.create.return_value = _mock_embeddings_response([[1.0, 0.0, 0.0]])
        matches = search_document_content(rest, client_id=1, query="what's the termination policy")

    assert matches[0].content == "termination clause text"
    assert matches[0].similarity > matches[1].similarity


def test_search_document_content_filters_by_doc_type(rest):
    rest.insert(
        "document_chunks",
        {"client_id": 1, "doc_type": "SOW", "version_number": 1, "chunk_index": 0,
         "content": "sow content", "embedding": [1.0, 0.0]},
    )
    rest.insert(
        "document_chunks",
        {"client_id": 1, "doc_type": "BRD", "version_number": 1, "chunk_index": 0,
         "content": "brd content", "embedding": [1.0, 0.0]},
    )

    with patch("app.services.embedding_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.embeddings.create.return_value = _mock_embeddings_response([[1.0, 0.0]])
        matches = search_document_content(rest, client_id=1, query="anything", doc_type="SOW")

    assert len(matches) == 1
    assert matches[0].doc_type == "SOW"


def test_search_document_content_scoped_to_one_client(rest):
    rest.insert(
        "document_chunks",
        {"client_id": 1, "doc_type": "SOW", "version_number": 1, "chunk_index": 0,
         "content": "acme's sow", "embedding": [1.0, 0.0]},
    )
    rest.insert(
        "document_chunks",
        {"client_id": 2, "doc_type": "SOW", "version_number": 1, "chunk_index": 0,
         "content": "globex's sow", "embedding": [1.0, 0.0]},
    )

    with patch("app.services.embedding_service.OpenAI") as MockOpenAI:
        MockOpenAI.return_value.embeddings.create.return_value = _mock_embeddings_response([[1.0, 0.0]])
        matches = search_document_content(rest, client_id=1, query="anything")

    assert len(matches) == 1
    assert matches[0].content == "acme's sow"
