"""dogs + people: franz. Zusatzfelder (FAPAC/Sexe, Laeuferlizenz/Club/Regionale)

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-10-30 12:00:00.000000

Fuers offizielle CNEAC-Ergebnisformular (Teilnehmer mit franz. Lizenz):
- dogs.fapac_no  = franz. Hundelizenz (FAPAC)
- dogs.sex       = Geschlecht des Hundes (M/F)
- people.fr_license_no = franz. Laeuferlizenz (N° licence)
- people.fr_club       = franz. Verein des Laeufers (Club)
- people.fr_regionale  = franz. Regionalverband (Régionale)

Alle Spalten nullable -> rein additiv, keine Auswirkung auf bestehende Daten.
"""
from alembic import op
import sqlalchemy as sa


revision = 'd8e9f0a1b2c3'
down_revision = 'c7d8e9f0a1b2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('dogs', sa.Column('fapac_no', sa.String(length=50), nullable=True))
    op.add_column('dogs', sa.Column('sex', sa.String(length=1), nullable=True))
    op.add_column('people', sa.Column('fr_license_no', sa.String(length=50), nullable=True))
    op.add_column('people', sa.Column('fr_club', sa.String(length=120), nullable=True))
    op.add_column('people', sa.Column('fr_regionale', sa.String(length=120), nullable=True))


def downgrade():
    op.drop_column('people', 'fr_regionale')
    op.drop_column('people', 'fr_club')
    op.drop_column('people', 'fr_license_no')
    op.drop_column('dogs', 'sex')
    op.drop_column('dogs', 'fapac_no')
