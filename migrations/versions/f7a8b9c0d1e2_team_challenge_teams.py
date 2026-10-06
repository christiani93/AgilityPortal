"""Team-Challenge: teams-Tabelle (2er-Team-Sonderformat)

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-10-06

Legt die `teams`-Tabelle an: ein Team verknüpft zwei Registrations desselben
Events (eine läuft Agility, die andere Jumping) derselben Grössenkategorie.
`external_id` ist der stabile Round-Trip-Schlüssel fürs Sync mit der
AgilitySoftware. Konzept: KONZEPT_Team-Challenge.md §3.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f7a8b9c0d1e2'
down_revision = 'e6f7a8b9c0d1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'teams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('external_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=True),
        sa.Column('category_code', sa.String(length=20), nullable=False),
        sa.Column('level', sa.String(length=10), nullable=False),
        sa.Column('member_agility_registration_id', sa.Integer(), nullable=False),
        sa.Column('member_jumping_registration_id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=10), nullable=False,
                  server_default='portal'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'],
                                name='fk_teams_event'),
        sa.ForeignKeyConstraint(['member_agility_registration_id'], ['registrations.id'],
                                name='fk_teams_member_agility'),
        sa.ForeignKeyConstraint(['member_jumping_registration_id'], ['registrations.id'],
                                name='fk_teams_member_jumping'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_id', name='uq_teams_external_id'),
        sa.CheckConstraint(
            "category_code in ('Small','Medium','Intermediate','Large')",
            name='ck_teams_category_code'),
        sa.CheckConstraint("level in ('soft','expert')", name='ck_teams_level'),
    )


def downgrade():
    op.drop_table('teams')
