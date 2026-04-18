"""add dog category and class_level

Revision ID: f6a3b8c9d2e1
Revises: e5f2a7b3c1d4
Create Date: 2026-04-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a3b8c9d2e1'
down_revision = 'e5f2a7b3c1d4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('dogs', sa.Column('category', sa.String(1), nullable=True))
    op.add_column('dogs', sa.Column('class_level', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('dogs', 'class_level')
    op.drop_column('dogs', 'category')
