"""add block_type and duration_minutes to schedule_blocks, relax constraints

Revision ID: k1f8g3h2i5j4
Revises: j0e7f2g1h4i5
Create Date: 2026-04-18 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'k1f8g3h2i5j4'
down_revision = 'j0e7f2g1h4i5'
branch_labels = None
depends_on = None


def upgrade():
    # Neue Spalten
    op.add_column('schedule_blocks',
        sa.Column('block_type', sa.String(20), nullable=False, server_default='run'))
    op.add_column('schedule_blocks',
        sa.Column('duration_minutes', sa.Integer(), nullable=True))

    # CHECK-Constraints entfernen (MySQL: drop + re-create ohne Constraint)
    # MySQL ignoriert benannte CHECK-Constraints vor 8.0, daher try/except
    with op.batch_alter_table('schedule_blocks') as batch_op:
        try:
            batch_op.drop_constraint('ck_schedule_blocks_class_level', type_='check')
        except Exception:
            pass
        try:
            batch_op.drop_constraint('ck_schedule_blocks_category_code', type_='check')
        except Exception:
            pass
        # Spalten nullable machen
        batch_op.alter_column('discipline',     existing_type=sa.String(20), nullable=True)
        batch_op.alter_column('category_code',  existing_type=sa.String(20), nullable=True)
        batch_op.alter_column('class_level',    existing_type=sa.Integer(), nullable=True)


def downgrade():
    with op.batch_alter_table('schedule_blocks') as batch_op:
        batch_op.alter_column('discipline',     existing_type=sa.String(20), nullable=False)
        batch_op.alter_column('category_code',  existing_type=sa.String(20), nullable=False)
        batch_op.alter_column('class_level',    existing_type=sa.Integer(), nullable=False)
    op.drop_column('schedule_blocks', 'duration_minutes')
    op.drop_column('schedule_blocks', 'block_type')
