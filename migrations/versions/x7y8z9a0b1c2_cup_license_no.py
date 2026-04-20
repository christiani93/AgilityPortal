"""cup: license_no für Titelverteidiger-Erkennung

Revision ID: x7y8z9a0b1c2
Revises: w6x7y8z9a0b1
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa

revision = 'x7y8z9a0b1c2'
down_revision = 'w6x7y8z9a0b1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('cup_qualified_teams',
                  sa.Column('license_no', sa.String(50), nullable=True))
    op.add_column('cup_final_participants',
                  sa.Column('license_no', sa.String(50), nullable=True))


def downgrade():
    op.drop_column('cup_final_participants', 'license_no')
    op.drop_column('cup_qualified_teams', 'license_no')
