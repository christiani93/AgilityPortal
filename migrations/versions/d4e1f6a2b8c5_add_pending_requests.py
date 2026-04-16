"""add pending_requests table

Revision ID: d4e1f6a2b8c5
Revises: c2d8e5f3b6a1
Create Date: 2026-04-16 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e1f6a2b8c5'
down_revision = 'c2d8e5f3b6a1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pending_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('request_type', sa.String(length=10), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='pending'),
        sa.Column('submitted_by_id', sa.Integer(), nullable=True),
        sa.Column('judge_ais_id', sa.Integer(), nullable=True),
        sa.Column('judge_first_name', sa.String(length=100), nullable=True),
        sa.Column('judge_last_name', sa.String(length=100), nullable=True),
        sa.Column('club_vereinsnummer', sa.String(length=20), nullable=True),
        sa.Column('club_name', sa.String(length=255), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('admin_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['submitted_by_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('pending_requests')
