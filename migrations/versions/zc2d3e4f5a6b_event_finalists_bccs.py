"""event_finalists: category + division für BCCS-SM (4 Divisionen I/L × SM/Nachwuchs)

SKBS-SM lässt beide NULL. Nullable → keine Datenmigration nötig.

Revision ID: zc2d3e4f5a6b
Revises: zb1c2d3e4f5a
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa


revision = 'zc2d3e4f5a6b'
down_revision = 'zb1c2d3e4f5a'
branch_labels = None
depends_on = None


def _column_exists(bind, table, column):
    cols = [c['name'] for c in sa.inspect(bind).get_columns(table)]
    return column in cols


def upgrade():
    bind = op.get_bind()
    for col in (
        sa.Column('category', sa.String(length=20), nullable=True),
        sa.Column('division', sa.String(length=20), nullable=True),
    ):
        if not _column_exists(bind, 'event_finalists', col.name):
            op.add_column('event_finalists', col)


def downgrade():
    bind = op.get_bind()
    for name in ('division', 'category'):
        if _column_exists(bind, 'event_finalists', name):
            op.drop_column('event_finalists', name)
