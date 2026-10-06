"""add dog breed (Rasse)

Revision ID: d1e2f3a4b5c6
Revises: a9b0c1d2e3f4
Create Date: 2026-10-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'd1e2f3a4b5c6'
down_revision = 'a9b0c1d2e3f4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('dogs', sa.Column('breed', sa.String(length=120), nullable=True))


def downgrade():
    op.drop_column('dogs', 'breed')
