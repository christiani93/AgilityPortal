"""add event_judges table

Revision ID: c2d8e5f3b6a1
Revises: b1e9c4f2a7d3
Create Date: 2026-04-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c2d8e5f3b6a1'
down_revision = 'b1e9c4f2a7d3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'event_judges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('judge_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ),
        sa.ForeignKeyConstraint(['judge_id'], ['judges.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', 'judge_id', name='uq_event_judge'),
    )


def downgrade():
    op.drop_table('event_judges')
