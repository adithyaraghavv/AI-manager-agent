"""add server-side timestamp defaults

Revision ID: fa5ad4cc9424
Revises: 50ec6baa0704
Create Date: 2026-07-31 05:53:31.072621

Fixes: clients.created_at, templates.uploaded_at, and client_documents.uploaded_at
previously relied on a Python-side default (SQLAlchemy's `default=`), which only
applies when the ORM itself builds the INSERT. Once inserts started going through
Supabase's REST API instead (app/db/rest_client.py), that default never fired and
Postgres rejected inserts on these NOT NULL columns. Moving the default to the
database itself (`server_default=now()`) fixes it for every access path, not just
whichever one happens to remember to set it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa5ad4cc9424'
down_revision: Union[str, Sequence[str], None] = '50ec6baa0704'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('clients', 'created_at', server_default=sa.text('now()'))
    op.alter_column('templates', 'uploaded_at', server_default=sa.text('now()'))
    op.alter_column('client_documents', 'uploaded_at', server_default=sa.text('now()'))


def downgrade() -> None:
    op.alter_column('clients', 'created_at', server_default=None)
    op.alter_column('templates', 'uploaded_at', server_default=None)
    op.alter_column('client_documents', 'uploaded_at', server_default=None)
