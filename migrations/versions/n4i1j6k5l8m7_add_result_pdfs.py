"""add result_pdfs table

Revision ID: n4i1j6k5l8m7
Revises: m3h0i5j4k7l6
Create Date: 2026-04-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'n4i1j6k5l8m7'
down_revision = 'm3h0i5j4k7l6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'result_pdfs',
        sa.Column('id',            sa.Integer(),      nullable=False),
        sa.Column('event_id',      sa.Integer(),      nullable=False),
        sa.Column('run_name',      sa.String(200),    nullable=True),
        sa.Column('ring',          sa.String(50),     nullable=True),
        sa.Column('discipline',    sa.String(30),     nullable=True),
        sa.Column('category_code', sa.String(20),     nullable=True),
        sa.Column('class_level',   sa.Integer(),      nullable=True),
        sa.Column('pdf_data',      sa.LargeBinary(),  nullable=False),
        sa.Column('is_final',      sa.Boolean(),      nullable=False, server_default=sa.false()),
        sa.Column('created_at',    sa.DateTime(),     nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_result_pdfs_event_id', 'result_pdfs', ['event_id'])


def downgrade():
    op.drop_index('ix_result_pdfs_event_id', table_name='result_pdfs')
    op.drop_table('result_pdfs')
