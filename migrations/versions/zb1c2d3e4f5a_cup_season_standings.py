"""cups: Saison-Ranglisten-Konfiguration (points_table, count_best_meetings, standings_disciplines)

Hintergrund: cup_standings.py wertet die Saisonpunkte über mehrere Meetings und
ruft cup.points_for_rank() + cup.count_best_meetings auf. Die zugehörigen Spalten
(point_system_json / count_best_meetings) wurden beim Quali-Rework (w6x7y8z9a0b1)
gedroppt → die öffentliche Cup-Rangliste war seither defekt. Diese Migration legt
die Konfiguration sauber neu an. Genutzt u.a. vom WiMeSma-Cup (nur Open+Jumping
zählen, Agility nicht).

Revision ID: zb1c2d3e4f5a
Revises: z9a0b1c2d3e4
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa


revision = 'zb1c2d3e4f5a'
down_revision = 'z9a0b1c2d3e4'
branch_labels = None
depends_on = None


def _column_exists(bind, table, column):
    cols = [c['name'] for c in sa.inspect(bind).get_columns(table)]
    return column in cols


def upgrade():
    bind = op.get_bind()
    new_columns = (
        sa.Column('points_table', sa.Text(), nullable=True),
        sa.Column('count_best_meetings', sa.Integer(), nullable=True),
        sa.Column('standings_disciplines', sa.Text(), nullable=True),
    )
    for col in new_columns:
        if not _column_exists(bind, 'cups', col.name):
            op.add_column('cups', col)


def downgrade():
    bind = op.get_bind()
    for name in ('standings_disciplines', 'count_best_meetings', 'points_table'):
        if _column_exists(bind, 'cups', name):
            op.drop_column('cups', name)
