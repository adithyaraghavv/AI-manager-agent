"""add team_assignments and document_responsibilities to sow_metadata

Revision ID: e2b7c4a9f1d3
Revises: d8a3f5c1e6b7
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e2b7c4a9f1d3'
down_revision: Union[str, Sequence[str], None] = 'd8a3f5c1e6b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('sow_metadata', sa.Column('team_assignments', sa.JSON(), nullable=True))
    op.add_column('sow_metadata', sa.Column('document_responsibilities', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('sow_metadata', 'document_responsibilities')
    op.drop_column('sow_metadata', 'team_assignments')
