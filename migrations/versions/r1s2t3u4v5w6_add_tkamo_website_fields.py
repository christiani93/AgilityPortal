"""add tkamo and website sync fields to events

Revision ID: r1s2t3u4v5w6
Revises: q7l4m9n8o1p0
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa

revision = 'r1s2t3u4v5w6'
down_revision = 'q7l4m9n8o1p0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('events', sa.Column('tkamo_disciplines',    sa.Text(),    nullable=True))
    op.add_column('events', sa.Column('tkamo_categories',     sa.Text(),    nullable=True))
    op.add_column('events', sa.Column('tkamo_judges',         sa.Text(),    nullable=True))
    op.add_column('events', sa.Column('tkamo_contact_email',  sa.String(255), nullable=True))
    op.add_column('events', sa.Column('tkamo_imported_at',    sa.DateTime(), nullable=True))
    op.add_column('events', sa.Column('event_description_de', sa.Text(),    nullable=True))
    op.add_column('events', sa.Column('website_synced_at',    sa.DateTime(), nullable=True))
    op.add_column('events', sa.Column('website_event_id',     sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('events', 'tkamo_disciplines')
    op.drop_column('events', 'tkamo_categories')
    op.drop_column('events', 'tkamo_judges')
    op.drop_column('events', 'tkamo_contact_email')
    op.drop_column('events', 'tkamo_imported_at')
    op.drop_column('events', 'event_description_de')
    op.drop_column('events', 'website_synced_at')
    op.drop_column('events', 'website_event_id')
