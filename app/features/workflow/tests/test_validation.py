"""L1 and L2 validation tests (#15, #16)."""

import io
import json
import zipfile
from types import SimpleNamespace

import pytest

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import DSMetaData, PublicationType
from app.features.workflow.models import ValidationStatus, WorkflowDataset, WorkflowVersion
from app.features.workflow.package import PackageValidator
from app.features.workflow.services import WorkflowDatasetService
from app.features.workflow.validation import L1Validator, L2Validator

pytestmark = pytest.mark.service

VALID_MANIFEST = """name: demo-workflow
version: 1.0.0
description: A demo workflow used by the validation tests
license: MIT
authors:
  - name: Ada Lovelace
    affiliation: Analytical Engine Lab
tags:
  - ci
  - demo
"""

VALID_YAML = """name: demo
on: push
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
"""

MISSING_ON_YAML = """name: Missing trigger
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - run: echo hi
"""

INVALID_JOB_YAML = """name: Invalid job
on: push
jobs:
  build:
    steps:
      - run: echo missing runs-on
"""

WRONG_TYPE_YAML = """name: Wrong type
on: push
jobs: not-a-mapping
"""


def make_workflow(owner_id, status=ValidationStatus.DRAFT):
    meta = DSMetaData(
        title="Validation workflow",
        description="L1/L2 validation fixture",
        publication_type=PublicationType.NONE,
    )
    db.session.add(meta)
    db.session.flush()
    dataset = WorkflowDataset(
        user_id=owner_id,
        ds_meta_data_id=meta.id,
        validation_status=status,
    )
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


def make_package_zip(workflow: str = VALID_YAML) -> bytes:
    files = {
        "actionhub.yaml": VALID_MANIFEST,
        "workflow.yml": workflow,
        "README.md": "# Demo workflow\n\nValidación L1 y L2.",
        "LICENSE": "MIT License\n\nCopyright (c) 2026",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


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


def test_validate_l1_version_does_not_bypass_l2(test_app, test_client):
    with test_app.app_context():
        owner = UserRepository().create(email="l1-no-bypass@example.com", password="secret")
        dataset = make_workflow(owner.id, status=ValidationStatus.DRAFT)
        version = make_version(dataset.id, INVALID_JOB_YAML)

        result = WorkflowDatasetService().validate_l1_version(version)

        assert result.valid is False
        assert dataset.validation_status == ValidationStatus.FAILED


def test_valid_workflow_passes_l2():
    result = L2Validator().validate_text(VALID_YAML)

    assert result.valid is True
    assert result.issues == []


def test_valid_workflow_file_passes_l2(tmp_path):
    path = tmp_path / "workflow.yml"
    path.write_text(VALID_YAML, encoding="utf-8")

    result = L2Validator().validate_file(path)

    assert result.valid is True


def test_missing_on_trigger_fails_l2():
    result = L2Validator().validate_text(MISSING_ON_YAML)

    assert result.valid is False
    assert result.issues
    assert "Esquema inválido" in result.issues[0].message
    assert "propiedad obligatoria" in result.issues[0].message


def test_job_without_runs_on_or_uses_fails_l2():
    result = L2Validator().validate_text(INVALID_JOB_YAML)

    assert result.valid is False
    assert result.issues
    assert any(issue.field == "jobs.build" for issue in result.issues)


def test_wrong_jobs_type_fails_l2_with_field():
    result = L2Validator().validate_text(WRONG_TYPE_YAML)

    assert result.valid is False
    assert any(issue.field == "jobs" for issue in result.issues)


def test_empty_yaml_fails_l2():
    result = L2Validator().validate_text("")

    assert result.valid is False
    assert result.issues


def test_validate_zip_blocks_workflow_with_invalid_schema():
    result = PackageValidator().validate_zip(make_package_zip(workflow=INVALID_JOB_YAML))

    assert result.valid is False
    assert result.issues
    assert all(issue.file == "workflow.yml" for issue in result.issues)
    assert any(issue.field == "jobs.build" for issue in result.issues)


def test_upload_package_does_not_persist_workflow_failing_l2(test_app, test_client, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    with test_app.app_context():
        user = UserRepository().create(email="l2-upload-invalid@example.com", password="secret")
        before = WorkflowDataset.query.count()
        storage = SimpleNamespace(read=lambda: make_package_zip(workflow=INVALID_JOB_YAML))

        dataset, issues = WorkflowDatasetService().upload_package(storage, user)

        assert dataset is None
        assert issues
        assert any(issue.file == "workflow.yml" for issue in issues)
        assert WorkflowDataset.query.count() == before
        assert not (tmp_path / "uploads").exists()


def test_valid_version_passes_l2_and_becomes_validated(test_app, test_client):
    with test_app.app_context():
        owner = UserRepository().create(email="l2-valid@example.com", password="secret")
        dataset = make_workflow(owner.id)
        version = make_version(dataset.id, VALID_YAML)

        result = WorkflowDatasetService().validate_l2_version(version)

        assert result.valid is True
        assert dataset.validation_status == ValidationStatus.VALIDATED


def test_invalid_version_blocks_validated_status_on_l2(test_app, test_client):
    with test_app.app_context():
        owner = UserRepository().create(email="l2-invalid@example.com", password="secret")
        dataset = make_workflow(owner.id, status=ValidationStatus.VALIDATED)
        version = make_version(dataset.id, INVALID_JOB_YAML)

        result = WorkflowDatasetService().validate_l2_version(version)

        assert result.valid is False
        assert dataset.validation_status == ValidationStatus.FAILED
        assert dataset.validation_status != ValidationStatus.VALIDATED


def test_service_text_validators_expose_l1_and_l2():
    service = WorkflowDatasetService()

    assert service.validate_l1_text(VALID_YAML).valid is True
    assert service.validate_l2_text(VALID_YAML).valid is True
    assert service.validate_l2_text(INVALID_JOB_YAML).valid is False


def test_unreadable_files_return_spanish_error_in_l1_and_l2(tmp_path):
    missing = tmp_path / "does-not-exist.yml"

    l1_result = L1Validator().validate_file(missing)
    l2_result = L2Validator().validate_file(missing)

    assert l1_result.valid is False
    assert "No se pudo leer el archivo" in l1_result.issues[0].message
    assert l2_result.valid is False
    assert "No se pudo leer el archivo" in l2_result.issues[0].message


def test_l2_translates_additional_properties_enum_and_min_items(tmp_path):
    extra_prop = (
        "name: Extra prop\n"
        "on: push\n"
        "unknown_root_key: true\n"
        "jobs:\n"
        "  build:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - run: echo hi\n"
    )
    extra_result = L2Validator().validate_text(extra_prop)
    assert extra_result.valid is False
    assert any("no se permiten propiedades adicionales" in issue.message for issue in extra_result.issues)

    schema_file = tmp_path / "mini.schema.json"
    schema_file.write_text(
        json.dumps(
            {
                "$schema": "http://json-schema.org/draft-07/schema#",
                "type": "object",
                "properties": {
                    "mode": {"enum": ["fast", "safe"]},
                    "items": {"type": "array", "minItems": 2},
                    "value": {"type": ["integer", "string"]},
                    "label": {"type": "string", "minLength": 5},
                },
            }
        ),
        encoding="utf-8",
    )
    validator = L2Validator(schema_path=schema_file)
    result = validator.validate_data({"mode": "invalid", "items": ["one"], "value": True, "label": "ab"})

    assert result.valid is False
    messages = [issue.message for issue in result.issues]
    assert any("valor no permitido" in message for message in messages)
    assert any("al menos 2 elemento" in message for message in messages)
    assert any("se esperaba uno de" in message for message in messages)
    assert any("is too short" in message for message in messages)
