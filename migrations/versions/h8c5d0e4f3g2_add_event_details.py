"""add event details: max_participants, entry_fee, notes_public

Revision ID: h8c5d0e4f3g2
Revises: g7b4c9d3e2f1
Create Date: 2026-04-18 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'h8c5d0e4f3g2'
down_revision = 'g7b4c9d3e2f1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('events', sa.Column('max_participants', sa.Integer(), nullable=True))
    op.add_column('events', sa.Column('entry_fee', sa.Numeric(10, 2), nullable=True))
    op.add_column('events', sa.Column('notes_public', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('events', 'notes_public')
    op.drop_column('events', 'entry_fee')
    op.drop_column('events', 'max_participants')
