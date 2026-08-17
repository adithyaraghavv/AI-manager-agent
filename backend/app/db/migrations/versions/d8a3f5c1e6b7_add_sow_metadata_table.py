"""add sow_metadata table

Revision ID: d8a3f5c1e6b7
Revises: c7f2a1e9d3b4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd8a3f5c1e6b7'
down_revision: Union[str, Sequence[str], None] = 'c7f2a1e9d3b4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'sow_metadata',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('client_id', sa.Integer(), sa.ForeignKey('clients.id'), nullable=False),
        sa.Column('contract_value', sa.String(), nullable=True),
        sa.Column('start_date', sa.String(), nullable=True),
        sa.Column('end_date', sa.String(), nullable=True),
        sa.Column('scope_summary', sa.String(), nullable=True),
        sa.Column('extracted_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.UniqueConstraint('client_id', name='uq_client_sow_metadata'),
    )


def downgrade() -> None:
    op.drop_table('sow_metadata')
