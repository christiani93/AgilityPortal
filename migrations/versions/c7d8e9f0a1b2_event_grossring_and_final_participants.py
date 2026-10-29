"""events: grossring_rings + final_participants (Zeitplan-Finalblock + Grossring)

Revision ID: c7d8e9f0a1b2
Revises: 482dc399fb65
Create Date: 2026-10-29 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c7d8e9f0a1b2'
down_revision = '482dc399fb65'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('events', sa.Column('grossring_rings', sa.Text(), nullable=True))
    op.add_column('events', sa.Column('final_participants', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('events', 'final_participants')
    op.drop_column('events', 'grossring_rings')
