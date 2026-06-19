"""results: total_faults für Gesamtfehlerpunkte aus AgilitySoftware

Revision ID: a1b2c3d4e5f6
Revises: z9a0b1c2d3e4
Create Date: 2026-05-30

Hintergrund: resultexport.v1.5 Schema-Erweiterung (additive). AgilitySoftware
exportiert ab Schema 3.1 das Feld total_faults (= internes fehler_total).
Alte Imports bleiben gültig (Feld nullable).
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'z9a0b1c2d3e4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('results') as batch_op:
        batch_op.add_column(sa.Column('total_faults', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('results') as batch_op:
        batch_op.drop_column('total_faults')
