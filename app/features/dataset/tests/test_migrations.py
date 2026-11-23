"""Migration 005 (#67): one view and download record per user, dataset and cookie.

The rest of the suite builds the schema with ``create_all``, so this test runs
the migration's own ``downgrade`` and ``upgrade`` against the test database:
both directions must work and the upgrade must remove the duplicates that the
old check-then-insert code could leave behind.
"""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import PublicationType
from app.features.dataset.repositories import DataSetRepository, DSMetaDataRepository

pytestmark = pytest.mark.integration

MIGRATION_005 = Path(__file__).resolve().parents[4] / "migrations" / "versions" / "005.py"
MIGRATION_006 = Path(__file__).resolve().parents[4] / "migrations" / "versions" / "006.py"
TABLES = (("ds_download_record", "download_date", "download_cookie"), ("ds_view_record", "view_date", "view_cookie"))


def load_migration(path):
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def columns(connection, table):
    return {column["name"] for column in inspect(connection).get_columns(table)}


def unique_constraints(connection, table):
    return {constraint["name"] for constraint in inspect(connection).get_unique_constraints(table)}


def tables(connection):
    return set(inspect(connection).get_table_names())


def test_migration_006_creates_version_one_and_can_be_undone(test_app, clean_database):
    migration = load_migration(MIGRATION_006)
    assert migration.revision == "006"
    assert migration.down_revision == "005"

    from app.features.workflow.models import WorkflowDataset, WorkflowVersion

    with test_app.app_context():
        owner = UserRepository().create(email="migration-006@example.com", password="secret")
        meta = DSMetaDataRepository().create(
            title="Legacy dataset",
            description="Published before versions existed",
            publication_type=PublicationType.NONE,
            dataset_doi="10.5072/legacy",
            deposition_id=12,
        )
        dataset_id = (
            DataSetRepository()
            .create(user_id=owner.id, ds_meta_data_id=meta.id, created_at=datetime.now(timezone.utc))
            .id
        )

        workflow_meta = DSMetaDataRepository().create(
            title="Legacy workflow",
            description="A workflow dataset",
            publication_type=PublicationType.NONE,
        )
        workflow = WorkflowDataset(
            user_id=owner.id,
            ds_meta_data_id=workflow_meta.id,
            manifest_json="{}",
            validation_status="validated",
        )
        db.session.add(workflow)
        db.session.flush()
        workflow_version = WorkflowVersion(
            workflow_dataset_id=workflow.id,
            manifest_json="{}",
            workflow_yaml="name: legacy\non: push\njobs: {}\n",
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(workflow_version)
        db.session.commit()
        workflow_id = workflow.id
        workflow_version_id = workflow_version.id
        db.session.remove()

        with db.engine.connect() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.downgrade()
                try:
                    assert "dataset_version" not in tables(connection)
                    assert "dataset_version_id" not in columns(connection, "feature_model")
                    assert "dataset_version_id" not in columns(connection, "workflow_version")
                    assert "conceptrecid" not in columns(connection, "ds_meta_data")

                    # A legacy feature model, created before versions existed.
                    connection.execute(
                        text("INSERT INTO feature_model (data_set_id) VALUES (:dataset_id)"),
                        {"dataset_id": dataset_id},
                    )

                    migration.upgrade()

                    assert "dataset_version" in tables(connection)
                    assert "conceptrecid" in columns(connection, "ds_meta_data")
                    assert "concept_doi" in columns(connection, "ds_meta_data")

                    version = connection.execute(
                        text(
                            "SELECT id, number, deposition_id, doi, published_at "
                            "FROM dataset_version WHERE dataset_id = :dataset_id"
                        ),
                        {"dataset_id": dataset_id},
                    ).one()
                    assert version.number == 1
                    assert version.deposition_id == 12
                    assert version.doi == "10.5072/legacy"
                    assert version.published_at is not None

                    feature_model_version = connection.execute(
                        text("SELECT dataset_version_id FROM feature_model WHERE data_set_id = :dataset_id"),
                        {"dataset_id": dataset_id},
                    ).scalar_one()
                    workflow_version_link = connection.execute(
                        text("SELECT dataset_version_id FROM workflow_version WHERE id = :id"),
                        {"id": workflow_version_id},
                    ).scalar_one()
                    workflow_version_row = connection.execute(
                        text("SELECT number, doi, published_at FROM dataset_version " "WHERE dataset_id = :dataset_id"),
                        {"dataset_id": workflow_id},
                    ).one()

                    assert feature_model_version == version.id
                    assert (
                        workflow_version_link
                        == connection.execute(
                            text("SELECT id FROM dataset_version WHERE dataset_id = :dataset_id"),
                            {"dataset_id": workflow_id},
                        ).scalar_one()
                    )
                    assert workflow_version_row.number == 1
                    assert workflow_version_row.doi is None
                    assert workflow_version_row.published_at is None
                finally:
                    if "dataset_version" not in tables(connection):
                        migration.upgrade()
            connection.commit()


def test_migration_005_removes_duplicates_and_can_be_undone(test_app, clean_database):
    migration = load_migration(MIGRATION_005)
    assert migration.revision == "005"
    assert migration.down_revision == "004"

    with test_app.app_context():
        owner = UserRepository().create(email="migration@example.com", password="secret")
        meta = DSMetaDataRepository().create(title="Migrated", description="d", publication_type=PublicationType.NONE)
        dataset_id = (
            DataSetRepository()
            .create(user_id=owner.id, ds_meta_data_id=meta.id, created_at=datetime.now(timezone.utc))
            .id
        )
        owner_id = owner.id
        db.session.remove()

        with db.engine.connect() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.downgrade()
                for table, _date, _cookie in TABLES:
                    assert "user_key" not in columns(connection, table)

                # What the old code could leave: repeated anonymous and user rows.
                for table, date, cookie in TABLES:
                    for user_id in (None, None, None, owner_id, owner_id):
                        connection.execute(
                            text(
                                f"INSERT INTO {table} (user_id, dataset_id, {date}, {cookie}) "
                                "VALUES (:u, :d, NOW(), 'c')"
                            ),
                            {"u": user_id, "d": dataset_id},
                        )

                migration.upgrade()

                for table, _date, _cookie in TABLES:
                    assert "user_key" in columns(connection, table)
                    assert any(name.endswith("_once") for name in unique_constraints(connection, table))
                    rows = connection.execute(text(f"SELECT user_id, user_key FROM {table} ORDER BY id")).all()
                    assert [tuple(row) for row in rows] == [(None, 0), (owner_id, owner_id)]
            connection.commit()
