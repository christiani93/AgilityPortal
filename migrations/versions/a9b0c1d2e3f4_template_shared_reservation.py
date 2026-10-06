"""Vorlagen-gesteuerte geteilte Reservation (Mehrtages-Serie)

Revision ID: a9b0c1d2e3f4
Revises: f7a8b9c0d1e2
Create Date: 2026-10-06

Fügt zwei Felder hinzu:
- event_templates.reservation_shared: aus dieser Vorlage erzeugte Turniere
  teilen sich EINE AdminPortal-Reservation.
- events.source_template_id: Provenienz-FK auf die Vorlage, aus der ein Turnier
  erzeugt wurde (nötig, um die „zuletzt erzeugte" Reservation einer Serie zu finden).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a9b0c1d2e3f4'
down_revision = 'f7a8b9c0d1e2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('event_templates', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'reservation_shared', sa.Boolean(), nullable=False,
            server_default=sa.false()))

    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('source_template_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_events_source_template', 'event_templates',
            ['source_template_id'], ['id'])


def downgrade():
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_constraint('fk_events_source_template', type_='foreignkey')
        batch_op.drop_column('source_template_id')

    with op.batch_alter_table('event_templates', schema=None) as batch_op:
        batch_op.drop_column('reservation_shared')
