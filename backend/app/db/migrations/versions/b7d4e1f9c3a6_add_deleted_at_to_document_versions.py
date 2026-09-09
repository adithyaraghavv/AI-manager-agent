"""add deleted_at to document_versions

Revision ID: b7d4e1f9c3a6
Revises: a3c8f6e2b9d4
Create Date: 2026-09-09 00:00:00.000000

Backs version_service.delete_version/restore_version — lets a single
specific version be deleted (its real file physically moved into a
"Recycle Bin" folder within the same storage backend, then restorable
back to its original path) without touching the rest of that document's
version history, distinct from client_documents.deleted_at which only
ever hides the CURRENT document as a whole.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7d4e1f9c3a6"
down_revision: Union[str, Sequence[str], None] = "a3c8f6e2b9d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "document_versions", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("document_versions", "deleted_at")
