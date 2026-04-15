"""add event_runs table

Revision ID: a3f7b2d1e4c8
Revises: 68c4313ed176
Create Date: 2026-04-15 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a3f7b2d1e4c8'
down_revision = '68c4313ed176'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'event_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('run_type', sa.String(length=20), nullable=False),
        sa.Column('category', sa.String(length=5), nullable=False),
        sa.Column('class_level', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('event_id', 'run_type', 'category', 'class_level',
                            name='uq_event_run'),
    )


def downgrade():
    op.drop_table('event_runs')
