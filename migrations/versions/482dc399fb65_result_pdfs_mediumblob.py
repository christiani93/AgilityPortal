"""result_pdfs.pdf_data auf MEDIUMBLOB erweitern (BLOB-Limit 64 KB trunkierte PDFs)

Revision ID: 482dc399fb65
Revises: f6a7b8c9d0e1
Create Date: 2026-10-09 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '482dc399fb65'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        'result_pdfs', 'pdf_data',
        existing_type=sa.LargeBinary(),
        type_=mysql.MEDIUMBLOB(),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        'result_pdfs', 'pdf_data',
        existing_type=mysql.MEDIUMBLOB(),
        type_=sa.LargeBinary(),
        existing_nullable=False,
    )
