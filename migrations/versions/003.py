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


def _workflow_data(connection):
    """Workflow datasets and workflow files that a downgrade would lose.

    Returns ``(datasets, files)``. Once ``type`` loses its ``workflow`` value
    those rows would come back as UVL datasets, and workflow files cannot
    exist without ``workflow_version_id``.
    """
    datasets = connection.execute(sa.text("SELECT COUNT(*) FROM data_set WHERE type = 'workflow'")).scalar()
    files = connection.execute(sa.text("SELECT COUNT(*) FROM file WHERE workflow_version_id IS NOT NULL")).scalar()
    return datasets, files


def downgrade():
    # MariaDB does not run DDL inside a transaction: a failure half way would
    # leave the schema half downgraded while alembic_version stays at 003.
    # Refuse before any DDL instead of deleting workflow data (and the view
    # and download records that reference its files).
    datasets, files = _workflow_data(op.get_bind())
    if datasets or files:
        raise RuntimeError(
            "Migration 003 cannot be undone while workflow data exists: "
            f"{datasets} workflow dataset(s) and {files} workflow file(s). "
            "Delete them before downgrading."
        )

    op.drop_constraint("ck_file_one_version", "file", type_="check")
    op.drop_constraint("fk_file_workflow_version", "file", type_="foreignkey")
    op.drop_column("file", "workflow_version_id")

    op.alter_column("file", "feature_model_id", existing_type=sa.Integer(), nullable=False)

    op.drop_table("workflow_version")

    op.drop_column("data_set", "package_format")
    op.drop_column("data_set", "actionlint_version")
    op.drop_column("data_set", "grade")
    op.drop_column("data_set", "security_score")
    op.drop_column("data_set", "validation_status")
    op.drop_column("data_set", "manifest_json")
