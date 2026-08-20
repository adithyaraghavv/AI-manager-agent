"""Retrieval-Augmented Generation (RAG) over document content.

A document's text is split into small overlapping chunks; each chunk gets
an embedding (a list of numbers capturing its meaning, via OpenAI) and is
stored in document_chunks (pgvector). To answer a content question, the
question itself is embedded the same way, and match_document_chunks (a
Postgres function, called via SupabaseRestClient.rpc) finds the chunks
whose meaning is closest — those get handed to the chat agent to answer
from, instead of the agent guessing or needing the whole document dumped
into its context.

Stage 2: every document type is embedded on upload, not just SOW (stage
1's scope). There's no doc_type allowlist here — a document is skipped
only if its text genuinely can't be extracted (see
app.core.text_extraction.TEXT_EXTRACTABLE_EXTENSIONS), the same "best
effort, never fatal" rule stage 1 already followed for SOW.

Documents uploaded before a doc_type was in scope (or before RAG existed
at all) don't get embedded retroactively just by this code shipping — see
app.db.backfill_embeddings for the one-off script that indexes what's
already on file.
"""

from dataclasses import dataclass

from openai import OpenAI

from app.config import settings
from app.core.text_extraction import extract_text
from app.db.rest_client import SupabaseRestClient

EMBEDDING_MODEL = "text-embedding-3-small"

# Character-based, not word-based — simplest thing that works for stage 1.
# Overlap keeps a sentence that straddles a chunk boundary from losing
# context on either side, for negligible extra cost.
CHUNK_SIZE_CHARS = 800
CHUNK_OVERLAP_CHARS = 100


def chunk_text(
    text: str, chunk_size: int = CHUNK_SIZE_CHARS, overlap: int = CHUNK_OVERLAP_CHARS
) -> list[str]:
    """Splits `text` into overlapping fixed-size chunks, oldest-to-newest order."""
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def _embed(texts: list[str]) -> list[list[float]]:
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


def _format_vector(embedding: list[float]) -> str:
    """Postgres's `vector` column type (pgvector) expects its input as the
    literal text "[0.1,0.2,...]" — sending a plain JSON array through
    PostgREST gets encoded as a Postgres ARRAY literal instead ("{0.1,0.2}"),
    which isn't valid syntax for `vector` and the database rejects with a
    400. This must be used for every embedding sent to Supabase, both on
    insert and as an RPC parameter."""
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


def embed_document(
    rest: SupabaseRestClient,
    client_id: int,
    doc_type: str,
    version_number: int,
    content: bytes,
    extension: str,
) -> int:
    """Chunks and embeds a document's text, replacing any prior chunks for
    this exact (client, doc_type, version) — safe to call again for the
    same upload. Returns the number of chunks stored.

    Never raises: an unreadable file or embedding API failure both just
    return 0. RAG indexing is a bonus on top of an upload, never a reason
    to fail the upload itself.
    """
    text = extract_text(content, extension)
    if not text:
        return 0

    # Postgres's text type flatly rejects a null byte ("22P05: unsupported
    # Unicode escape sequence") — some PDFs' extracted text can contain one
    # (a known pypdf quirk on certain malformed/scanned files), so strip it
    # before it ever reaches the database rather than crash the insert.
    text = text.replace("\x00", "")
    if not text:
        return 0

    pieces = chunk_text(text)
    if not pieces:
        return 0

    try:
        embeddings = _embed(pieces)
    except Exception:
        return 0

    rest.delete(
        "document_chunks",
        client_id=client_id,
        doc_type=doc_type,
        version_number=version_number,
    )
    for index, (piece, embedding) in enumerate(zip(pieces, embeddings)):
        rest.insert(
            "document_chunks",
            {
                "client_id": client_id,
                "doc_type": doc_type,
                "version_number": version_number,
                "chunk_index": index,
                "content": piece,
                "embedding": _format_vector(embedding),
            },
        )
    return len(pieces)


@dataclass
class ContentMatch:
    doc_type: str
    version_number: int
    chunk_index: int
    content: str
    similarity: float


def search_document_content(
    rest: SupabaseRestClient,
    client_id: int,
    query: str,
    doc_type: str | None = None,
    top_k: int = 5,
) -> list[ContentMatch]:
    """Finds the passages whose meaning is closest to `query`, across every
    embedded document for this client (or just `doc_type` if given)."""
    [query_embedding] = _embed([query])
    rows = rest.rpc(
        "match_document_chunks",
        {
            "query_embedding": _format_vector(query_embedding),
            "match_client_id": client_id,
            "match_doc_type": doc_type,
            "match_count": top_k,
        },
    )
    return [
        ContentMatch(
            doc_type=row["doc_type"],
            version_number=row["version_number"],
            chunk_index=row["chunk_index"],
            content=row["content"],
            similarity=row["similarity"],
        )
        for row in rows
    ]