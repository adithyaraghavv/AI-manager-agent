"""add deleted_at to client_documents

Revision ID: a3c8f6e2b9d4
Revises: f4a9c2e7b8d1
Create Date: 2026-09-06 00:00:00.000000

Backs client_service.delete_client_document/restore_client_document — lets
a single filed document be soft-deleted (hidden from status/dashboard/
search/RAG content search, but its storage_path row, version history, and
actual file left completely untouched) and restored via chat, the same
"hidden but recoverable" pattern clients.deleted_at already provides.

dashboard_service.py has defensively checked `doc.get("deleted_at")` on
client_documents rows for a while, which made it easy to assume this
column already existed — it didn't; a dict .get() on a genuinely missing
key just silently returns None. This migration actually adds it.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a3c8f6e2b9d4"
down_revision: Union[str, Sequence[str], None] = "f4a9c2e7b8d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "client_documents", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("client_documents", "deleted_at")
