"""dataset versions and concept DOI

Revision ID: 006
Revises: 005
Create Date: 2026-11-23 22:00:00.000000

Implements the design approved in #35 (``docs/dominio/versioning-design.md``):

- every dataset gets a ``dataset_version`` row; existing ones become version 1
  with the deposition and DOI their metadata already had;
- ``feature_model`` and ``workflow_version`` point at the version that owns
  them;
- ``ds_meta_data`` stores the concept identity returned by Zenodo/fakenodo.

The migration does not move files: #37 reads version 1 from the old folder
when ``v1/`` does not exist yet.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def _duplicate_workflow_versions(connection):
    """Workflow datasets with more than one WorkflowVersion.

    ``workflow_version.dataset_version_id`` is unique: one workflow version is
    the content of one dataset version. Before #38 creates new versions, every
    workflow has at most one. Refuse to invent numbers or DOIs if that changed.
    """
    return connection.execute(
        sa.text(
            """
            SELECT workflow_dataset_id, COUNT(*) AS total
            FROM workflow_version
            GROUP BY workflow_dataset_id
            HAVING COUNT(*) > 1
            ORDER BY workflow_dataset_id
            """
        )
    ).fetchall()


def upgrade():
    connection = op.get_bind()

    duplicates = _duplicate_workflow_versions(connection)
    if duplicates:
        datasets = ", ".join(str(row[0]) for row in duplicates)
        raise RuntimeError(
            "Migration 006 needs one workflow_version per workflow dataset; "
            f"these datasets have more: {datasets}. Split them before migrating."
        )

    op.add_column("ds_meta_data", sa.Column("conceptrecid", sa.Integer(), nullable=True))
    op.add_column("ds_meta_data", sa.Column("concept_doi", sa.String(length=120), nullable=True))

    op.create_table(
        "dataset_version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("dataset_id", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("deposition_id", sa.Integer(), nullable=True),
        sa.Column("doi", sa.String(length=120), nullable=True),
        sa.Column("change_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["data_set.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "number", name="uq_dataset_version_number"),
    )

    op.add_column("feature_model", sa.Column("dataset_version_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_feature_model_dataset_version",
        "feature_model",
        "dataset_version",
        ["dataset_version_id"],
        ["id"],
    )

    op.add_column("workflow_version", sa.Column("dataset_version_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_workflow_version_dataset_version",
        "workflow_version",
        "dataset_version",
        ["dataset_version_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_workflow_version_dataset_version",
        "workflow_version",
        ["dataset_version_id"],
    )

    # Existing datasets become version 1. A non-null DOI makes it published;
    # the file layout is left untouched for #37's compatibility path.
    connection.execute(
        sa.text(
            """
            INSERT INTO dataset_version
                (dataset_id, number, deposition_id, doi, created_at, published_at)
            SELECT ds.id, 1, md.deposition_id, md.dataset_doi, ds.created_at,
                   CASE WHEN md.dataset_doi IS NOT NULL THEN ds.created_at ELSE NULL END
            FROM data_set ds
            JOIN ds_meta_data md ON md.id = ds.ds_meta_data_id
            """
        )
    )

    connection.execute(
        sa.text(
            """
            UPDATE feature_model
            SET dataset_version_id = (
                SELECT dv.id
                FROM dataset_version dv
                WHERE dv.dataset_id = feature_model.data_set_id AND dv.number = 1
            )
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE workflow_version
            SET dataset_version_id = (
                SELECT dv.id
                FROM dataset_version dv
                WHERE dv.dataset_id = workflow_version.workflow_dataset_id AND dv.number = 1
            )
            """
        )
    )


def downgrade():
    # MySQL refuses to drop a unique index while a foreign key still uses it,
    # so the FK goes first.
    op.drop_constraint("fk_workflow_version_dataset_version", "workflow_version", type_="foreignkey")
    op.drop_constraint("uq_workflow_version_dataset_version", "workflow_version", type_="unique")
    op.drop_column("workflow_version", "dataset_version_id")

    op.drop_constraint("fk_feature_model_dataset_version", "feature_model", type_="foreignkey")
    op.drop_column("feature_model", "dataset_version_id")

    op.drop_table("dataset_version")

    op.drop_column("ds_meta_data", "concept_doi")
    op.drop_column("ds_meta_data", "conceptrecid")
