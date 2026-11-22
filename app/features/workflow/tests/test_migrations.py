"""Migration 004 (#17): ``workflow_version.metadata_json``.

The rest of the suite builds the schema with ``create_all``, so this test
runs the migration's own ``downgrade`` and ``upgrade`` against the test
database to check that both directions work.
"""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect

from app import db

pytestmark = pytest.mark.integration

MIGRATION_004 = Path(__file__).resolve().parents[4] / "migrations" / "versions" / "004.py"


def load_migration(path):
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def workflow_version_columns(connection):
    return {column["name"] for column in inspect(connection).get_columns("workflow_version")}


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
