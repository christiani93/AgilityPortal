"""add is_test flag to events

Revision ID: l2g9h4i3j6k5
Revises: k1f8g3h2i5j4
Create Date: 2026-04-18 22:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'l2g9h4i3j6k5'
down_revision = 'k1f8g3h2i5j4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('events',
        sa.Column('is_test', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column('events', 'is_test')
