"""add startnumber_schema and run_time_config to events

Revision ID: m3h0i5j4k7l6
Revises: l2g9h4i3j6k5
Create Date: 2026-04-18 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'm3h0i5j4k7l6'
down_revision = 'l2g9h4i3j6k5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('events', sa.Column('startnumber_schema', sa.Text(), nullable=True))
    op.add_column('events', sa.Column('run_time_config',   sa.Text(), nullable=True))


def downgrade():
    op.drop_column('events', 'run_time_config')
    op.drop_column('events', 'startnumber_schema')
