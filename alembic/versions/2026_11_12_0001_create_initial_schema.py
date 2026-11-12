"""create initial schema

Revision ID: 0001
Revises: 
Create Date: 2026-11-12 17:24:14.513501

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('ads',
    sa.Column('id', sa.Text(), nullable=False),
    sa.Column('source', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('price', sa.Integer(), nullable=True),
    sa.Column('town', sa.Text(), nullable=True),
    sa.Column('published_date', sa.Text(), nullable=True),
    sa.Column('link', sa.Text(), nullable=False),
    sa.Column('query', sa.Text(), nullable=True),
    sa.Column('first_seen', sa.Text(), nullable=True),
    sa.Column('photo', sa.Text(), nullable=True),
    sa.Column('currency', sa.Text(), nullable=True),
    sa.Column('price_converted', sa.Integer(), server_default='0', nullable=False),
    sa.Column('price_label', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('source', 'id', name=op.f('pk_ads'))
    )
    op.create_table('watches',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('query', sa.Text(), nullable=True),
    sa.Column('max_price', sa.Integer(), nullable=True),
    sa.Column('min_price', sa.Integer(), nullable=True),
    sa.Column('is_active', sa.Integer(), server_default='1', nullable=False),
    sa.Column('created_at', sa.Text(), nullable=True),
    sa.Column('city', sa.Text(), server_default='', nullable=False),
    sa.Column('state', sa.Text(), server_default='', nullable=False),
    sa.Column('exact', sa.Integer(), server_default='0', nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_watches')),
    sa.UniqueConstraint('user_id', 'query', 'max_price', 'min_price', 'city', 'state', 'exact', name=op.f('uq_watches_user_id')),
    sqlite_autoincrement=True
    )
    op.create_table('favorites',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('ad_id', sa.Text(), nullable=False),
    sa.Column('ad_source', sa.Text(), nullable=False),
    sa.Column('saved_at', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['ad_source', 'ad_id'], ['ads.source', 'ads.id'], name=op.f('fk_favorites_ad_source_ads')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_favorites')),
    sa.UniqueConstraint('user_id', 'ad_id', 'ad_source', name=op.f('uq_favorites_user_id')),
    sqlite_autoincrement=True
    )
    op.create_table('price_history',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('ad_id', sa.Text(), nullable=False),
    sa.Column('ad_source', sa.Text(), nullable=False),
    sa.Column('price', sa.Integer(), nullable=False),
    sa.Column('changed_at', sa.Text(), nullable=True),
    sa.Column('currency', sa.Text(), nullable=True),
    sa.ForeignKeyConstraint(['ad_source', 'ad_id'], ['ads.source', 'ads.id'], name=op.f('fk_price_history_ad_source_ads')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_price_history')),
    sqlite_autoincrement=True
    )


def downgrade() -> None:
    op.drop_table('price_history')
    op.drop_table('favorites')
    op.drop_table('watches')
    op.drop_table('ads')
