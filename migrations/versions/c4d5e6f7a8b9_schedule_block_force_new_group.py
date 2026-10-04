"""schedule_blocks: force_new_group (erzwungener Gruppen-Split)

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-10-04

Erlaubt, an einem Block eine neue Umbau-/Briefing-Gruppe zu erzwingen, auch wenn
Disziplin+Klasse mit dem Vorgänger-Block übereinstimmen. Anwendungsfall: Klasse 3
mit getrennten Briefings für Large/Intermediate und Medium/Small innerhalb der
gleichen Disziplin+Klasse (Läufe dazwischen sonst fälschlich in einer Gruppe).
Default False, bestehende Blöcke bleiben unverändert.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d5e6f7a8b9'
down_revision = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('schedule_blocks', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'force_new_group', sa.Boolean(), nullable=False,
            server_default=sa.false()))


def downgrade():
    with op.batch_alter_table('schedule_blocks', schema=None) as batch_op:
        batch_op.drop_column('force_new_group')
