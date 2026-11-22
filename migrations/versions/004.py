"""add extracted metadata to workflow versions

Revision ID: 004
Revises: 003
Create Date: 2026-11-20 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workflow_version", sa.Column("metadata_json", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("workflow_version", "metadata_json")
