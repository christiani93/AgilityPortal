"""add event lizenzcheck_report

Revision ID: q7l4m9n8o1p0
Revises: p6k3l8m7n0o9
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa

revision = 'q7l4m9n8o1p0'
down_revision = 'p6k3l8m7n0o9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('events', sa.Column('lizenzcheck_report', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('events', 'lizenzcheck_report')
