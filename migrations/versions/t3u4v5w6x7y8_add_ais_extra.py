"""add ais_turniernummer_extra

Revision ID: t3u4v5w6x7y8
Revises: s2t3u4v5w6x7
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa

revision = 't3u4v5w6x7y8'
down_revision = 's2t3u4v5w6x7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'events',
        sa.Column('ais_turniernummer_extra', sa.String(255), nullable=True)
    )


def downgrade():
    op.drop_column('events', 'ais_turniernummer_extra')
