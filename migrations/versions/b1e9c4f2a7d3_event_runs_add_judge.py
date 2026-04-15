"""event_runs: add judge_id

Revision ID: b1e9c4f2a7d3
Revises: a3f7b2d1e4c8
Create Date: 2026-04-15 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1e9c4f2a7d3'
down_revision = 'a3f7b2d1e4c8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('event_runs',
        sa.Column('judge_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_event_runs_judge_id', 'event_runs', 'judges',
        ['judge_id'], ['id']
    )


def downgrade():
    op.drop_constraint('fk_event_runs_judge_id', 'event_runs', type_='foreignkey')
    op.drop_column('event_runs', 'judge_id')
