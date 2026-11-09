"""schedule_blocks.judge_id: direkter Richter für Blöcke ohne EventRun-Link
(block_type=="final" - American/KO-Finale fasst mehrere Kategorien/Klassen
zusammen, hat keinen einzelnen fachlichen Lauf). "run"-Blöcke bleiben beim
EventRun als Richter-Quelle.

Revision ID: sb01judge
Revises: bccs001
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa


revision = 'sb01judge'
down_revision = 'bccs001'
branch_labels = None
depends_on = None


def _column_exists(bind, table, column):
    cols = [c['name'] for c in sa.inspect(bind).get_columns(table)]
    return column in cols


def upgrade():
    bind = op.get_bind()
    if not _column_exists(bind, 'schedule_blocks', 'judge_id'):
        op.add_column('schedule_blocks', sa.Column('judge_id', sa.Integer(), nullable=True))
        with op.batch_alter_table('schedule_blocks') as batch_op:
            batch_op.create_foreign_key(
                'fk_schedule_blocks_judge_id', 'judges', ['judge_id'], ['id'])


def downgrade():
    bind = op.get_bind()
    if _column_exists(bind, 'schedule_blocks', 'judge_id'):
        with op.batch_alter_table('schedule_blocks') as batch_op:
            batch_op.drop_constraint('fk_schedule_blocks_judge_id', type_='foreignkey')
            batch_op.drop_column('judge_id')
