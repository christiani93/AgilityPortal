"""Add skbs_sm field to registrations table.

Eigenständiger Per-Anmeldung-Marker für die SKBS-Schweizermeisterschaft (analog
bccs_sm / is_fmbb). Nötig, weil am selben Large-Event Teilnehmer nur SM, nur
FMBB-Quali, beides oder gar keine Sonderwertung laufen können. Vom Veranstalter
gesetzt; wird im Event-Paket exportiert und von der AgilitySoftware als
entry["skbs_sm"] für den SKBS-SM-Teilnehmerfilter gelesen.

Revision ID: skbs001
Revises: fmbb001
Create Date: 2026-11-23 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'skbs001'
down_revision = 'fmbb001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('registrations', sa.Column('skbs_sm', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('registrations', 'skbs_sm')
