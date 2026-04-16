"""add user person_id

Revision ID: e5f2a7b3c1d4
Revises: d4e1f6a2b8c5
Create Date: 2026-04-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e5f2a7b3c1d4'
down_revision = 'd4e1f6a2b8c5'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('person_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_users_person_id',
        'users', 'people',
        ['person_id'], ['id']
    )


def downgrade():
    op.drop_constraint('fk_users_person_id', 'users', type_='foreignkey')
    op.drop_column('users', 'person_id')
