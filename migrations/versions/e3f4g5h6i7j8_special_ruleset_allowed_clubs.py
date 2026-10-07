"""add special_ruleset_allowed_clubs (Spezialturnier-Freigabe pro Verein)

Revision ID: e3f4g5h6i7j8
Revises: d1e2f3a4b5c6
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa

revision = 'e3f4g5h6i7j8'
down_revision = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'special_ruleset_allowed_clubs',
        sa.Column('id',      sa.Integer(), nullable=False),
        sa.Column('ruleset', sa.String(length=50), nullable=False),
        sa.Column('club_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name='fk_srac_club'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ruleset', 'club_id', name='uq_special_ruleset_allowed_club'),
    )


def downgrade():
    op.drop_table('special_ruleset_allowed_clubs')
