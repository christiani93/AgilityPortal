"""person account_user_id + club_id (Mehr-Läufer-Konto, Verein pro Läufer)

Revision ID: a2b3c4d5e6f7
Revises: 791a305093be
Create Date: 2026-11-02 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a2b3c4d5e6f7'
down_revision = '791a305093be'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('people', schema=None) as batch_op:
        batch_op.add_column(sa.Column('account_user_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('club_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_people_account_user_id', 'users', ['account_user_id'], ['id'])
        batch_op.create_foreign_key(
            'fk_people_club_id', 'clubs', ['club_id'], ['id'])

    # Backfill: die eigene Person jedes Kontos bekommt account_user_id gesetzt,
    # damit sie in User.handlers erscheint.
    op.execute(
        "UPDATE people SET account_user_id = "
        "(SELECT u.id FROM users u WHERE u.person_id = people.id) "
        "WHERE account_user_id IS NULL "
        "AND EXISTS (SELECT 1 FROM users u WHERE u.person_id = people.id)"
    )


def downgrade():
    with op.batch_alter_table('people', schema=None) as batch_op:
        batch_op.drop_constraint('fk_people_club_id', type_='foreignkey')
        batch_op.drop_constraint('fk_people_account_user_id', type_='foreignkey')
        batch_op.drop_column('club_id')
        batch_op.drop_column('account_user_id')
