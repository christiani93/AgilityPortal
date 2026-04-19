"""add event payment_info

Revision ID: p6k3l8m7n0o9
Revises: o5j2k7l6m9n8
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa

revision = 'p6k3l8m7n0o9'
down_revision = 'o5j2k7l6m9n8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('events', sa.Column('payment_info', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('events', 'payment_info')
