"""add registration start_number

Revision ID: g7b4c9d3e2f1
Revises: f6a3b8c9d2e1
Create Date: 2026-04-18 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'g7b4c9d3e2f1'
down_revision = 'f6a3b8c9d2e1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('registrations', sa.Column('start_number', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('registrations', 'start_number')
