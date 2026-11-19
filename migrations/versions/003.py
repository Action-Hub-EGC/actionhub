"""add workflow dataset type

Revision ID: 003
Revises: 002
Create Date: 2026-11-18 17:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "workflow_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workflow_dataset_id", sa.Integer(), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("workflow_yaml", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workflow_dataset_id"], ["data_set.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column("data_set", sa.Column("manifest_json", sa.Text(), nullable=True))
    op.add_column(
        "data_set",
        sa.Column("validation_status", sa.String(length=20), nullable=False, server_default="draft"),
    )
    op.add_column("data_set", sa.Column("security_score", sa.Integer(), nullable=True))
    op.add_column("data_set", sa.Column("grade", sa.String(length=1), nullable=True))
    op.add_column("data_set", sa.Column("actionlint_version", sa.String(length=40), nullable=True))
    op.add_column("data_set", sa.Column("package_format", sa.String(length=20), nullable=True))

    op.alter_column("file", "feature_model_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("file", sa.Column("workflow_version_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_file_workflow_version",
        "file",
        "workflow_version",
        ["workflow_version_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_file_one_version",
        "file",
        "(feature_model_id IS NOT NULL AND workflow_version_id IS NULL) OR "
        "(feature_model_id IS NULL AND workflow_version_id IS NOT NULL)",
    )


def downgrade():
    op.drop_constraint("ck_file_one_version", "file", type_="check")
    op.drop_constraint("fk_file_workflow_version", "file", type_="foreignkey")
    op.drop_column("file", "workflow_version_id")

    # Workflow files cannot exist once the type is removed.
    op.execute("DELETE FROM file WHERE feature_model_id IS NULL")
    op.alter_column("file", "feature_model_id", existing_type=sa.Integer(), nullable=False)

    op.drop_table("workflow_version")

    op.drop_column("data_set", "package_format")
    op.drop_column("data_set", "actionlint_version")
    op.drop_column("data_set", "grade")
    op.drop_column("data_set", "security_score")
    op.drop_column("data_set", "validation_status")
    op.drop_column("data_set", "manifest_json")
