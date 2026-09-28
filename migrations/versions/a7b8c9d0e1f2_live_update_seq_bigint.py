"""live_updates.sequence_no auf BigInteger (INT-Overflow-Fix)

Revision ID: a7b8c9d0e1f2
Revises: 29338e5310b1
Create Date: 2026-09-28

Die AgilitySoftware erzeugt sequence_no aus einem Millisekunden-Epoch (~13-stellig,
z.B. 1790535644886). Die Spalte war ein 32-Bit-INT (Max 2147483647); MySQL kappte
den Wert im nicht-strikten Modus still auf das Maximum, wodurch ALLE Live-Updates
mit sequence_no=2147483647 landeten und ab dem 2. Push pro (Event, Gerät) den
UNIQUE-Constraint uq_live_updates_event_device_seq verletzten -> 500-Loop auf
POST /api/liveupdate.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7b8c9d0e1f2'
down_revision = '29338e5310b1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('live_updates', schema=None) as batch_op:
        batch_op.alter_column(
            'sequence_no',
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )


def downgrade():
    with op.batch_alter_table('live_updates', schema=None) as batch_op:
        batch_op.alter_column(
            'sequence_no',
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
