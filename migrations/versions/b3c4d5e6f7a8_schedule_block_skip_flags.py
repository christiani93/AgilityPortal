"""schedule_blocks: skip_changeover / skip_briefing (Gruppen-Overrides)

Revision ID: b3c4d5e6f7a8
Revises: a7b8c9d0e1f2
Create Date: 2026-10-02

Erlaubt, pro Lauf-Gruppe (gesteuert über den ersten Block der Gruppe) den Umbau
und/oder das Briefing aus der Zeitberechnung zu nehmen. Anwendungsfall: z.B. das
Open der Klasse 1 folgt ohne eigenen Umbau/Briefing direkt auf das Agility derselben
Klasse. Beide Flags defaulten auf False (= wird eingerechnet), bestehende Blöcke
bleiben also unverändert.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3c4d5e6f7a8'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('schedule_blocks', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'skip_changeover', sa.Boolean(), nullable=False,
            server_default=sa.false()))
        batch_op.add_column(sa.Column(
            'skip_briefing', sa.Boolean(), nullable=False,
            server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('schedule_blocks', schema=None) as batch_op:
        batch_op.drop_column('skip_briefing')
        batch_op.drop_column('skip_changeover')
