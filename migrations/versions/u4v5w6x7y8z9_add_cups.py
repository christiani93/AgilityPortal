"""add cups, cup_events, cup_finals and bracket tables

Revision ID: u4v5w6x7y8z9
Revises: t3u4v5w6x7y8
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa

revision = 'u4v5w6x7y8z9'
down_revision = 't3u4v5w6x7y8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('season', sa.Integer(), nullable=False),
        sa.Column('special_ruleset', sa.String(50), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('point_system_json', sa.Text(), nullable=True),
        sa.Column('count_best_meetings', sa.Integer(), nullable=True),
        sa.Column('split_by_class', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('split_by_run_type', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'cup_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cup_id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('meeting_no', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['cup_id'], ['cups.id']),
        sa.ForeignKeyConstraint(['event_id'], ['events.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cup_id', 'event_id', name='uq_cup_events_cup_event'),
    )

    op.create_table(
        'cup_finals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cup_id', sa.Integer(), nullable=False),
        sa.Column('group_label', sa.String(100), nullable=False),
        sa.Column('category_code', sa.String(20), nullable=False),
        sa.Column('class_level', sa.Integer(), nullable=True),
        sa.Column('is_published', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['cup_id'], ['cups.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'cup_final_participants',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('final_id', sa.Integer(), nullable=False),
        sa.Column('dog_name', sa.String(120), nullable=False),
        sa.Column('handler_name', sa.String(120), nullable=False),
        sa.Column('qualifying_points', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('draw_number', sa.Integer(), nullable=True),
        sa.Column('seeding_rank', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['final_id'], ['cup_finals.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'cup_final_matchups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('final_id', sa.Integer(), nullable=False),
        sa.Column('round_no', sa.Integer(), nullable=False),
        sa.Column('matchup_no', sa.Integer(), nullable=False),
        sa.Column('matchup_type', sa.String(20), nullable=False, server_default='winner'),
        sa.Column('participant_a_id', sa.Integer(), nullable=True),
        sa.Column('a_time1', sa.Float(), nullable=True),
        sa.Column('a_time2', sa.Float(), nullable=True),
        sa.Column('a_faults', sa.Integer(), nullable=True),
        sa.Column('a_refusals', sa.Integer(), nullable=True),
        sa.Column('a_disqualified', sa.Boolean(), nullable=True),
        sa.Column('participant_b_id', sa.Integer(), nullable=True),
        sa.Column('b_time1', sa.Float(), nullable=True),
        sa.Column('b_time2', sa.Float(), nullable=True),
        sa.Column('b_faults', sa.Integer(), nullable=True),
        sa.Column('b_refusals', sa.Integer(), nullable=True),
        sa.Column('b_disqualified', sa.Boolean(), nullable=True),
        sa.Column('winner_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['final_id'], ['cup_finals.id']),
        sa.ForeignKeyConstraint(['participant_a_id'], ['cup_final_participants.id']),
        sa.ForeignKeyConstraint(['participant_b_id'], ['cup_final_participants.id']),
        sa.ForeignKeyConstraint(['winner_id'], ['cup_final_participants.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'cup_final_results',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('final_id', sa.Integer(), nullable=False),
        sa.Column('participant_id', sa.Integer(), nullable=False),
        sa.Column('final_rank', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['final_id'], ['cup_finals.id']),
        sa.ForeignKeyConstraint(['participant_id'], ['cup_final_participants.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('cup_final_results')
    op.drop_table('cup_final_matchups')
    op.drop_table('cup_final_participants')
    op.drop_table('cup_finals')
    op.drop_table('cup_events')
    op.drop_table('cups')
