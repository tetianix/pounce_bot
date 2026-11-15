"""add shown_hints

Revision ID: d67650411149
Revises: 0001
Create Date: 2026-11-15 22:44:56.394657

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd67650411149'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('shown_hints',
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('hint', sa.Text(), nullable=False),
    sa.Column('shown_at', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('user_id', 'hint', name=op.f('pk_shown_hints'))
    )


def downgrade() -> None:
    op.drop_table('shown_hints')
