"""add dataset type discriminator

Revision ID: 002
Revises: 001
Create Date: 2026-11-18 16:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "data_set",
        sa.Column("type", sa.String(length=20), nullable=False, server_default="uvl"),
    )


def downgrade():
    op.drop_column("data_set", "type")
