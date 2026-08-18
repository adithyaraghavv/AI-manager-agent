"""add document_chunks table and vector search function for RAG

Revision ID: f4a9c2e7b8d1
Revises: e2b7c4a9f1d3
Create Date: 2026-08-17 00:00:00.000000

Stage 1 of the RAG (Retrieval-Augmented Generation) pipeline: lets the chat
agent answer questions using a document's actual content instead of just
handing over the file. A document's text is split into small chunks; each
chunk gets an embedding (a list of numbers capturing its meaning) via
OpenAI, stored here using pgvector — a Postgres extension Supabase already
supports, so this needs no new infrastructure.

Written as raw SQL (not SQLAlchemy's op.create_table) because the `vector`
column type isn't a stock SQLAlchemy type, and match_document_chunks is a
stored function, not a table.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f4a9c2e7b8d1'
down_revision: Union[str, Sequence[str], None] = 'e2b7c4a9f1d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# OpenAI's text-embedding-3-small produces 1536-number vectors.
EMBEDDING_DIMENSIONS = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(f"""
        CREATE TABLE document_chunks (
            id SERIAL PRIMARY KEY,
            client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
            doc_type VARCHAR NOT NULL,
            version_number INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding VECTOR({EMBEDDING_DIMENSIONS}) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE (client_id, doc_type, version_number, chunk_index)
        )
    """)

    # ivfflat: an approximate-nearest-neighbor index, so similarity search
    # stays fast as chunk count grows instead of scanning every row.
    op.execute("""
        CREATE INDEX document_chunks_embedding_idx
        ON document_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    """)

    # Exposed to the app via PostgREST's /rpc/ endpoint (SupabaseRestClient.rpc) —
    # cosine similarity ("<=>") isn't something a plain REST filter can express,
    # so this one query lives as a stored function instead.
    op.execute(f"""
        CREATE OR REPLACE FUNCTION match_document_chunks(
            query_embedding VECTOR({EMBEDDING_DIMENSIONS}),
            match_client_id INTEGER,
            match_doc_type VARCHAR DEFAULT NULL,
            match_count INTEGER DEFAULT 5
        )
        RETURNS TABLE (
            id INTEGER,
            doc_type VARCHAR,
            version_number INTEGER,
            chunk_index INTEGER,
            content TEXT,
            similarity FLOAT
        )
        LANGUAGE sql STABLE
        AS $$
            SELECT id, doc_type, version_number, chunk_index, content,
                   1 - (embedding <=> query_embedding) AS similarity
            FROM document_chunks
            WHERE client_id = match_client_id
              AND (match_doc_type IS NULL OR doc_type = match_doc_type)
            ORDER BY embedding <=> query_embedding
            LIMIT match_count
        $$
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS match_document_chunks")
    op.execute("DROP TABLE IF EXISTS document_chunks")
