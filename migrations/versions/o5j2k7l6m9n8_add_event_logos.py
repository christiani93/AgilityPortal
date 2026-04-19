"""add event logo columns

Revision ID: o5j2k7l6m9n8
Revises: n4i1j6k5l8m7
Create Date: 2026-04-19 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'o5j2k7l6m9n8'
down_revision = 'n4i1j6k5l8m7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('events', sa.Column('event_logo_filename', sa.String(255), nullable=True))
    op.add_column('events', sa.Column('club_logo_filename',  sa.String(255), nullable=True))


def downgrade():
    op.drop_column('events', 'club_logo_filename')
    op.drop_column('events', 'event_logo_filename')
