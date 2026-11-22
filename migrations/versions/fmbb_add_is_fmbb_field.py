"""Add is_fmbb field to registrations table.

Per-Anmeldung-Marker für die FMBB-WM-Quali (analog bccs_sm). Vom Veranstalter
gesetzt; wird im Event-Paket exportiert und von der AgilitySoftware als
entry["is_fmbb"] für die FMBB-Quali-Auswertung gelesen.

Revision ID: fmbb001
Revises: sb01judge
Create Date: 2026-11-22 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'fmbb001'
down_revision = 'sb01judge'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('registrations', sa.Column('is_fmbb', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('registrations', 'is_fmbb')
