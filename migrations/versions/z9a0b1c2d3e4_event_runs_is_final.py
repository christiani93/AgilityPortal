"""event_runs: is_final Flag + Constraint-Erweiterung für SKBS-SM-Finallauf

Revision ID: z9a0b1c2d3e4
Revises: y8z9a0b1c2d3
Create Date: 2026-05-28
"""
from alembic import op
import sqlalchemy as sa


revision = 'z9a0b1c2d3e4'
down_revision = 'y8z9a0b1c2d3'
branch_labels = None
depends_on = None


def _column_exists(bind, table, column):
    cols = [c['name'] for c in sa.inspect(bind).get_columns(table)]
    return column in cols


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'mysql':
        # MySQL: uq_event_run wird vom event_id-FK als Backing-Index benutzt.
        # → DROP INDEX scheitert direkt. Workaround: neuen Index unter anderem
        #   Namen anlegen, dann den alten droppen (MySQL nimmt automatisch den
        #   neuen als FK-Backing), dann optional umbenennen.
        if not _column_exists(bind, 'event_runs', 'is_final'):
            op.add_column('event_runs',
                          sa.Column('is_final', sa.Boolean(), nullable=False,
                                    server_default=sa.false()))
        op.execute("ALTER TABLE event_runs ADD UNIQUE KEY uq_event_run_v2 "
                   "(event_id, run_type, category, class_level, is_final)")
        op.execute("ALTER TABLE event_runs DROP INDEX uq_event_run")
        op.execute("ALTER TABLE event_runs RENAME INDEX uq_event_run_v2 TO uq_event_run")
    else:
        # SQLite & andere: batch-Mode (re-create-table) klappt sauber.
        with op.batch_alter_table('event_runs') as batch_op:
            if not _column_exists(bind, 'event_runs', 'is_final'):
                batch_op.add_column(
                    sa.Column('is_final', sa.Boolean(), nullable=False,
                              server_default=sa.false())
                )
            batch_op.drop_constraint('uq_event_run', type_='unique')
            batch_op.create_unique_constraint(
                'uq_event_run',
                ['event_id', 'run_type', 'category', 'class_level', 'is_final'],
            )


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'mysql':
        op.execute("ALTER TABLE event_runs ADD UNIQUE KEY uq_event_run_v2 "
                   "(event_id, run_type, category, class_level)")
        op.execute("ALTER TABLE event_runs DROP INDEX uq_event_run")
        op.execute("ALTER TABLE event_runs RENAME INDEX uq_event_run_v2 TO uq_event_run")
        if _column_exists(bind, 'event_runs', 'is_final'):
            op.drop_column('event_runs', 'is_final')
    else:
        with op.batch_alter_table('event_runs') as batch_op:
            batch_op.drop_constraint('uq_event_run', type_='unique')
            batch_op.create_unique_constraint(
                'uq_event_run',
                ['event_id', 'run_type', 'category', 'class_level'],
            )
            batch_op.drop_column('is_final')
