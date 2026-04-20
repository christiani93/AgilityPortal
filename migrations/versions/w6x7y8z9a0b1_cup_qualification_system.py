"""rework cup qualification: add qual_runs and qualified_teams tables

Revision ID: w6x7y8z9a0b1
Revises: v5w6x7y8z9a0
Create Date: 2026-04-20
"""
from alembic import op
import sqlalchemy as sa

revision = 'w6x7y8z9a0b1'
down_revision = 'v5w6x7y8z9a0'
branch_labels = None
depends_on = None


def upgrade():
    # cups-Tabelle: alte Punkte-Spalten entfernen, neue Quali-Spalten hinzufügen
    op.add_column('cups', sa.Column('title_defender_spots', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('cups', sa.Column('wildcard_spots', sa.Integer(), nullable=False, server_default='0'))

    # Alte Spalten aus der ersten Migration (können NULL sein, daher safe)
    try:
        op.drop_column('cups', 'point_system_json')
    except Exception:
        pass
    try:
        op.drop_column('cups', 'count_best_meetings')
    except Exception:
        pass
    try:
        op.drop_column('cups', 'split_by_run_type')
    except Exception:
        pass
    # split_by_class bleibt (wird weiterhin genutzt)

    # Neue Tabelle: Qualifikationsläufe
    op.create_table(
        'cup_qualification_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cup_id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('discipline', sa.String(30), nullable=False),
        sa.Column('spots', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('spots_json', sa.Text(), nullable=True),
        sa.Column('split_by_class', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('run_order', sa.Integer(), nullable=False),
        sa.Column('is_fillup', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('label', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['cup_id'], ['cups.id']),
        sa.ForeignKeyConstraint(['event_id'], ['events.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # Neue Tabelle: Qualifizierte Teams
    op.create_table(
        'cup_qualified_teams',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cup_id', sa.Integer(), nullable=False),
        sa.Column('category_code', sa.String(20), nullable=False),
        sa.Column('class_level', sa.Integer(), nullable=True),
        sa.Column('dog_name', sa.String(120), nullable=False),
        sa.Column('handler_name', sa.String(120), nullable=False),
        sa.Column('qualification_source', sa.String(20), nullable=False),
        sa.Column('qual_run_id', sa.Integer(), nullable=True),
        sa.Column('qualified_rank', sa.Integer(), nullable=True),
        sa.Column('seeding_note', sa.String(200), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['cup_id'], ['cups.id']),
        sa.ForeignKeyConstraint(['qual_run_id'], ['cup_qualification_runs.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('cup_qualified_teams')
    op.drop_table('cup_qualification_runs')
    op.drop_column('cups', 'title_defender_spots')
    op.drop_column('cups', 'wildcard_spots')
