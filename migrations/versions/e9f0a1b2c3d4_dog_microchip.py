"""dogs.microchip: Chip-/Transpondernummer des Hundes

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-11-01 18:00:00.000000

Optionales Feld, u.a. fuers deutsche VDH-Formular "Bestaetigung fuer
Auslandsergebnisse". Wird ins Event-Paket exportiert
(entities.dogs[].chip -> AgilitySoftware dogs.json "Chip").

Spalte nullable -> rein additiv, keine Auswirkung auf bestehende Daten.
"""
from alembic import op
import sqlalchemy as sa


revision = 'e9f0a1b2c3d4'
down_revision = 'd8e9f0a1b2c3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('dogs', sa.Column('microchip', sa.String(length=50), nullable=True))


def downgrade():
    op.drop_column('dogs', 'microchip')
