"""add not_applicable_documents table

Revision ID: c7f2a1e9d3b4
Revises: b1e4b5b9006f
Create Date: 2026-08-12 13:30:00.000000

Lets a PM mark a document type as not required for a specific client (e.g.
Requirement Analysis docs don't apply because the client already handed
over finished requirements in the SOW). Gating treats a marked doc_type
the same as an existing one instead of permanently flagging it missing.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c7f2a1e9d3b4"
down_revision: Union[str, Sequence[str], None] = "b1e4b5b9006f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "not_applicable_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "client_id", sa.Integer(), sa.ForeignKey("clients.id"), nullable=False
        ),
        sa.Column("doc_type", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("marked_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "client_id", "doc_type", name="uq_client_doc_not_applicable"
        ),
    )


def downgrade() -> None:
    op.drop_table("not_applicable_documents")
