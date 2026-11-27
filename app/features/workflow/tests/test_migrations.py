"""Migrations 003 (#12) and 004 (#17) of the workflow dataset type.

The rest of the suite builds the schema with ``create_all``, so these tests
run the migrations' own ``downgrade`` and ``upgrade`` against the test
database to check that both directions work, and that 003 refuses to drop
workflow data.
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
from app.features.dataset.models import DSMetaData, PublicationType
from app.features.hubfile.models import Hubfile, HubfileDownloadRecord, HubfileViewRecord
from app.features.workflow.models import WorkflowDataset, WorkflowVersion

pytestmark = pytest.mark.integration

MIGRATIONS = Path(__file__).resolve().parents[4] / "migrations" / "versions"
MIGRATION_003 = MIGRATIONS / "003.py"
MIGRATION_004 = MIGRATIONS / "004.py"


def load_migration(path):
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def workflow_version_columns(connection):
    return {column["name"] for column in inspect(connection).get_columns("workflow_version")}


def file_columns(connection):
    return {column["name"] for column in inspect(connection).get_columns("file")}


def file_check_constraints(connection):
    return {constraint["name"] for constraint in inspect(connection).get_check_constraints("file")}


def test_migration_003_downgrade_refuses_with_workflow_data(test_app, clean_database):
    migration = load_migration(MIGRATION_003)
    assert migration.revision == "003"
    assert migration.down_revision == "002"

    with test_app.app_context():
        owner = UserRepository().create(email="migration-003@example.com", password="secret")
        meta = DSMetaData(title="Workflow", description="d", publication_type=PublicationType.NONE)
        db.session.add(meta)
        db.session.flush()
        workflow = WorkflowDataset(user_id=owner.id, ds_meta_data_id=meta.id, manifest_json="{}")
        db.session.add(workflow)
        db.session.flush()
        version = WorkflowVersion(
            workflow_dataset_id=workflow.id,
            manifest_json="{}",
            workflow_yaml="name: demo\non: push\njobs: {}\n",
            created_at=datetime.now(timezone.utc),
        )
        db.session.add(version)
        db.session.flush()
        hubfile = Hubfile(name="ci.yml", checksum="abc", size=10, workflow_version_id=version.id)
        db.session.add(hubfile)
        db.session.flush()
        # The records that made the old ``DELETE FROM file`` fail with 1451.
        db.session.add(HubfileViewRecord(file_id=hubfile.id, view_cookie="c"))
        db.session.add(HubfileDownloadRecord(file_id=hubfile.id, download_cookie="c"))
        db.session.commit()
        db.session.remove()

        with db.engine.connect() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                with pytest.raises(RuntimeError, match=r"1 workflow dataset\(s\) and 1 workflow file\(s\)"):
                    migration.downgrade()

                # Nothing was dropped before the refusal.
                assert "workflow_version" in inspect(connection).get_table_names()
                assert "workflow_version_id" in file_columns(connection)
                assert "ck_file_one_version" in file_check_constraints(connection)
                assert "validation_status" in {column["name"] for column in inspect(connection).get_columns("data_set")}
                assert connection.execute(text("SELECT COUNT(*) FROM file")).scalar() == 1
                assert connection.execute(text("SELECT type FROM data_set")).scalar() == "workflow"


def test_migration_003_counts_workflow_data(test_app, clean_database):
    migration = load_migration(MIGRATION_003)

    with test_app.app_context():
        db.session.remove()
        with db.engine.connect() as connection:
            assert migration._workflow_data(connection) == (0, 0)


def test_migration_004_downgrade_and_upgrade(test_app):
    migration = load_migration(MIGRATION_004)
    assert migration.revision == "004"
    assert migration.down_revision == "003"

    with test_app.app_context():
        db.session.remove()
        with db.engine.connect() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                assert "metadata_json" in workflow_version_columns(connection)
                try:
                    migration.downgrade()
                    assert "metadata_json" not in workflow_version_columns(connection)
                finally:
                    if "metadata_json" not in workflow_version_columns(connection):
                        migration.upgrade()
                assert "metadata_json" in workflow_version_columns(connection)
            connection.commit()
