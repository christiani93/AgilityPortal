"""add reservation_id and reservation_synced_at to events

Revision ID: s2t3u4v5w6x7
Revises: r1s2t3u4v5w6
Create Date: 2026-04-19 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 's2t3u4v5w6x7'
down_revision = 'r1s2t3u4v5w6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('events', sa.Column('reservation_id', sa.Integer(), nullable=True))
    op.add_column('events', sa.Column('reservation_synced_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('events', 'reservation_synced_at')
    op.drop_column('events', 'reservation_id')
