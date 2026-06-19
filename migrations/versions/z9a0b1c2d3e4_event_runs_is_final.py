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


def upgrade():
    with op.batch_alter_table('event_runs') as batch_op:
        batch_op.add_column(
            sa.Column('is_final', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.drop_constraint('uq_event_run', type_='unique')
        batch_op.create_unique_constraint(
            'uq_event_run',
            ['event_id', 'run_type', 'category', 'class_level', 'is_final'],
        )


def downgrade():
    with op.batch_alter_table('event_runs') as batch_op:
        batch_op.drop_constraint('uq_event_run', type_='unique')
        batch_op.create_unique_constraint(
            'uq_event_run',
            ['event_id', 'run_type', 'category', 'class_level'],
        )
        batch_op.drop_column('is_final')
