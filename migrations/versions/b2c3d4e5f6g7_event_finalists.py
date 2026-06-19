"""event_finalists: Persistierung der von AgilitySoftware berechneten SKBS-SM-Finalisten

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-30

Schema resultexport.v1.6 — Software exportiert finalists.json, Portal persistiert
sie. Beim erneuten Import wird die Liste pro Event ersetzt (idempotent).
"""
from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'event_finalists',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=False),
        sa.Column('license', sa.String(length=50), nullable=True),
        sa.Column('dog_name', sa.String(length=120), nullable=True),
        sa.Column('handler_name', sa.String(length=120), nullable=True),
        sa.Column('source', sa.String(length=30), nullable=True),
        sa.Column('from_class', sa.Integer(), nullable=True),
        sa.Column('quali_rank', sa.Integer(), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('imported_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_event_finalists_event', 'event_finalists', ['event_id'])


def downgrade():
    op.drop_index('ix_event_finalists_event', table_name='event_finalists')
    op.drop_table('event_finalists')
