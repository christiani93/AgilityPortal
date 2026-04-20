"""add forfeit field to cup_final_matchups

Revision ID: v5w6x7y8z9a0
Revises: u4v5w6x7y8z9
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa

revision = 'v5w6x7y8z9a0'
down_revision = 'u4v5w6x7y8z9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'cup_final_matchups',
        sa.Column('forfeit_participant_id', sa.Integer(), nullable=True)
    )
    # Foreign-Key-Constraint (optional, MySQL unterstützt ALTER TABLE ADD CONSTRAINT)
    op.create_foreign_key(
        'fk_cup_final_matchups_forfeit',
        'cup_final_matchups', 'cup_final_participants',
        ['forfeit_participant_id'], ['id']
    )


def downgrade():
    op.drop_constraint('fk_cup_final_matchups_forfeit', 'cup_final_matchups', type_='foreignkey')
    op.drop_column('cup_final_matchups', 'forfeit_participant_id')
