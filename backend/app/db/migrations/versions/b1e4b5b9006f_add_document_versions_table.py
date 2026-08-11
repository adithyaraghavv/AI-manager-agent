"""add document_versions table

Revision ID: b1e4b5b9006f
Revises: fa5ad4cc9424
Create Date: 2026-08-10 09:15:00.000000

Adds document version history: every upload for a (client, doc_type) now
creates a new row here instead of overwriting the previous one.
client_documents keeps pointing at the current version only; this table is
the full, append-only history — never updated, never deleted by normal app
code.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1e4b5b9006f'
down_revision: Union[str, Sequence[str], None] = 'fa5ad4cc9424'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'document_versions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('doc_type', sa.String(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('storage_path', sa.String(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('uploaded_by', sa.String(), nullable=True),
        sa.Column('comment', sa.String(), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.UniqueConstraint('client_id', 'doc_type', 'version_number', name='uq_client_doc_version'),
    )


def downgrade() -> None:
    op.drop_table('document_versions')
