"""L1 validation tests (#15)."""

import pytest

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import DSMetaData, PublicationType
from app.features.workflow.models import ValidationStatus, WorkflowDataset, WorkflowVersion
from app.features.workflow.services import WorkflowDatasetService
from app.features.workflow.validation import L1Validator

pytestmark = pytest.mark.service

VALID_YAML = """name: demo
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""


def make_workflow(owner_id, status=ValidationStatus.DRAFT):
    meta = DSMetaData(
        title="L1 workflow",
        description="L1 validation fixture",
        publication_type=PublicationType.NONE,
    )
    db.session.add(meta)
    db.session.flush()
    dataset = WorkflowDataset(user_id=owner_id, ds_meta_data_id=meta.id, validation_status=status)
    db.session.add(dataset)
    db.session.flush()
    return dataset


def make_version(dataset_id, workflow_yaml):
    version = WorkflowVersion(
        workflow_dataset_id=dataset_id,
        manifest_json="{}",
        workflow_yaml=workflow_yaml,
    )
    db.session.add(version)
    db.session.commit()
    return version


def test_valid_yaml_passes_l1():
    result = L1Validator().validate_text(VALID_YAML)

    assert result.valid is True
    assert result.issues == []


def test_malformed_yaml_reports_a_line():
    result = L1Validator().validate_text("name: demo\non: push\njobs:\n  build: [\n")

    assert result.valid is False
    assert result.issues
    assert result.issues[0].line is not None
    assert "YAML inválido" in result.issues[0].message


def test_duplicate_keys_are_rejected_with_a_line():
    result = L1Validator().validate_text("name: first\nname: second\n")

    assert result.valid is False
    assert result.issues
    assert result.issues[0].line == 2
    assert "Clave duplicada" in result.issues[0].message


def test_valid_file_passes_l1(tmp_path):
    path = tmp_path / "workflow.yml"
    path.write_text(VALID_YAML, encoding="utf-8")

    result = L1Validator().validate_file(path)

    assert result.valid is True


def test_valid_version_moves_workflow_to_validated(test_app, test_client):
    with test_app.app_context():
        owner = UserRepository().create(email="l1-valid@example.com", password="secret")
        dataset = make_workflow(owner.id)
        version = make_version(dataset.id, VALID_YAML)

        result = WorkflowDatasetService().validate_l1_version(version)

        assert result.valid is True
        assert dataset.validation_status == ValidationStatus.VALIDATED


def test_invalid_version_blocks_validated_status(test_app, test_client):
    with test_app.app_context():
        owner = UserRepository().create(email="l1-invalid@example.com", password="secret")
        dataset = make_workflow(owner.id, status=ValidationStatus.VALIDATED)
        version = make_version(dataset.id, "name: first\nname: second\n")

        result = WorkflowDatasetService().validate_l1_version(version)

        assert result.valid is False
        assert dataset.validation_status == ValidationStatus.FAILED
        assert dataset.validation_status != ValidationStatus.VALIDATED
