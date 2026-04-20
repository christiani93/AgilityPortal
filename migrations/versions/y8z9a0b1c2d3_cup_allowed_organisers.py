"""cup: allowed organisers (Veranstalter-Einschränkung pro Cup)

Revision ID: y8z9a0b1c2d3
Revises: x7y8z9a0b1c2
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa

revision = 'y8z9a0b1c2d3'
down_revision = 'x7y8z9a0b1c2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'cup_allowed_organisers',
        sa.Column('id',      sa.Integer(), nullable=False),
        sa.Column('cup_id',  sa.Integer(), nullable=False),
        sa.Column('club_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['cup_id'],  ['cups.id'],  name='fk_cao_cup'),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.id'], name='fk_cao_club'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('cup_id', 'club_id', name='uq_cup_allowed_org'),
    )


def downgrade():
    op.drop_table('cup_allowed_organisers')
