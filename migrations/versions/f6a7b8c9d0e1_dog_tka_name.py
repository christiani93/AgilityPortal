"""add dogs.tka_name (offizieller TKAMO-Lizenzcheck-Name, getrennt vom AOA-Namen)

Revision ID: f6a7b8c9d0e1
Revises: e3f4g5h6i7j8
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e1'
down_revision = 'e3f4g5h6i7j8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('dogs', sa.Column('tka_name', sa.String(length=120), nullable=True))


def downgrade():
    op.drop_column('dogs', 'tka_name')
