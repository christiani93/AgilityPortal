"""add in_season fields: registrations.is_in_season, events.bitches_in_season_start_last

Revision ID: i9d6e1f5g4h3
Revises: h8c5d0e4f3g2
Create Date: 2026-04-18 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'i9d6e1f5g4h3'
down_revision = 'h8c5d0e4f3g2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('registrations', sa.Column('is_in_season', sa.Boolean(), nullable=False, server_default='0'))
    op.add_column('events', sa.Column('bitches_in_season_start_last', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('registrations', 'is_in_season')
    op.drop_column('events', 'bitches_in_season_start_last')
