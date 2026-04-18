"""add schedule fields: ScheduleBlock.judge_id/title, Event.ring_count/ring_start_times

Revision ID: j0e7f2g1h4i5
Revises: i9d6e1f5g4h3
Create Date: 2026-04-18 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'j0e7f2g1h4i5'
down_revision = 'i9d6e1f5g4h3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('schedule_blocks', sa.Column('judge_id', sa.Integer(), nullable=True))
    op.add_column('schedule_blocks', sa.Column('title', sa.String(200), nullable=True))
    op.create_foreign_key('fk_schedule_blocks_judge', 'schedule_blocks', 'judges', ['judge_id'], ['id'])
    op.add_column('events', sa.Column('ring_count', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('events', sa.Column('ring_start_times', sa.Text(), nullable=True))


def downgrade():
    op.drop_constraint('fk_schedule_blocks_judge', 'schedule_blocks', type_='foreignkey')
    op.drop_column('schedule_blocks', 'title')
    op.drop_column('schedule_blocks', 'judge_id')
    op.drop_column('events', 'ring_start_times')
    op.drop_column('events', 'ring_count')
