"""schedule_blocks: participant_count_override

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-04

Manuelle Teilnehmerzahl pro Block für die Zeitplan-Berechnung (Briefing-/Laufdauer),
falls noch keine Online-Anmeldungen im Portal vorliegen (z.B. extern organisierte
Events wie LiTyWee). Hat Vorrang vor der aus Registration gezählten Zahl, wenn gesetzt.
Nullable, Default NULL = bestehendes Verhalten (Registration-Zählung) unverändert.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd5e6f7a8b9c0'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('schedule_blocks', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'participant_count_override', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('schedule_blocks', schema=None) as batch_op:
        batch_op.drop_column('participant_count_override')
