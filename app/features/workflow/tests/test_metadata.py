"""Workflow metadata extraction tests (#17)."""

import io
import json
from types import SimpleNamespace

import pytest

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import DSMetaData, PublicationType
from app.features.workflow.metadata import MetadataError, WorkflowMetadataExtractor
from app.features.workflow.models import ValidationStatus, WorkflowDataset, WorkflowVersion
from app.features.workflow.services import WorkflowDatasetService
from app.features.workflow.tests.test_package import make_zip

pytestmark = pytest.mark.service

CI_WORKFLOW = """name: CI
on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:
jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - run: ruff check .
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
        python: ["3.11", "3.12"]
        include:
          - os: macos-latest
            python: "3.12"
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
"""

REUSABLE_WORKFLOW = """on: [push, pull_request]
jobs:
  call:
    uses: octo-org/shared/.github/workflows/build.yml@v1
    with:
      target: prod
  deploy:
    needs: call
    runs-on: [self-hosted, linux]
    steps:
      - uses: ./.github/actions/deploy
"""


def extract(text):
    return WorkflowMetadataExtractor().extract_text(text)


@pytest.mark.parametrize(
    ("on", "expected"),
    [
        ("on: push", ["push"]),
        ("on: [push, pull_request]", ["push", "pull_request"]),
        ("on:\n  push:\n    branches: [main]\n  schedule:\n    - cron: '0 0 * * *'", ["push", "schedule"]),
        ("on:\n  workflow_dispatch:", ["workflow_dispatch"]),
    ],
    ids=["string", "list", "map", "map-with-null-value"],
)
def test_triggers_handle_the_three_forms_of_on(on, expected):
    metadata = extract(f"{on}\njobs: {{}}\n")

    assert metadata.triggers == expected


def test_on_parsed_as_yaml_11_boolean_key_is_still_read():
    metadata = WorkflowMetadataExtractor().extract({True: ["push"], "jobs": {}})

    assert metadata.triggers == ["push"]


def test_missing_on_gives_no_triggers():
    assert extract("jobs: {}\n").triggers == []


def test_jobs_runners_and_actions_are_extracted():
    metadata = extract(CI_WORKFLOW)

    assert metadata.name == "CI"
    assert [job.id for job in metadata.jobs] == ["lint", "test"]
    assert metadata.jobs[0].name == "Lint"
    assert metadata.jobs[0].runs_on == ["ubuntu-latest"]
    assert metadata.actions == ["actions/checkout@v4", "actions/setup-python@v5"]
    assert metadata.reusable_workflows == []


def test_matrix_runner_is_resolved_to_its_values():
    test_job = extract(CI_WORKFLOW).jobs[1]

    assert test_job.runs_on == ["ubuntu-latest", "windows-latest", "macos-latest"]
    assert test_job.matrix == {"os": ["ubuntu-latest", "windows-latest"], "python": ["3.11", "3.12"]}


def test_runners_are_unique_across_jobs():
    assert extract(CI_WORKFLOW).runners == ["ubuntu-latest", "windows-latest", "macos-latest"]


def test_unresolvable_matrix_expression_is_kept_as_written():
    text = (
        "on: push\njobs:\n  build:\n    runs-on: ${{ matrix.runner }}\n"
        "    strategy:\n      matrix: ${{ fromJSON(inputs.m) }}\n"
    )

    assert extract(text).runners == ["${{ matrix.runner }}"]


def test_reusable_workflows_and_label_lists():
    metadata = extract(REUSABLE_WORKFLOW)

    assert metadata.reusable_workflows == ["octo-org/shared/.github/workflows/build.yml@v1"]
    assert metadata.jobs[0].uses == "octo-org/shared/.github/workflows/build.yml@v1"
    assert metadata.jobs[0].runs_on == []
    assert metadata.runners == ["self-hosted", "linux"]
    assert metadata.actions == ["./.github/actions/deploy"]


def test_runs_on_group_form_is_read():
    text = "on: push\njobs:\n  build:\n    runs-on:\n      group: large\n      labels: [ubuntu-22.04]\n"

    assert extract(text).runners == ["large", "ubuntu-22.04"]


def test_metadata_round_trips_through_json():
    metadata = extract(CI_WORKFLOW)

    assert json.loads(metadata.to_json()) == metadata.to_dict()


def test_non_mapping_document_is_rejected():
    with pytest.raises(MetadataError):
        extract("- just\n- a list\n")


def upload(owner, workflow_yaml):
    package = SimpleNamespace(read=lambda: make_zip(workflow=workflow_yaml))
    return WorkflowDatasetService().upload_package(package, owner)


def test_uploaded_package_stores_the_metadata_of_its_version(test_app, test_client, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    with test_app.app_context():
        owner = UserRepository().create(email="metadata-upload@example.com", password="secret")

        dataset, issues = upload(owner, CI_WORKFLOW)

        assert issues == []
        version = dataset.latest_version()
        assert version.metadata_json is not None
        assert version.workflow_metadata["triggers"] == ["push", "pull_request", "workflow_dispatch"]
        assert dataset.workflow_metadata()["runners"] == ["ubuntu-latest", "windows-latest", "macos-latest"]


def test_rejected_package_stores_no_metadata(test_app, test_client, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    with test_app.app_context():
        owner = UserRepository().create(email="metadata-rejected@example.com", password="secret")
        before = WorkflowVersion.query.count()

        dataset, issues = upload(owner, "- just\n- a list\n")

        assert dataset is None
        assert issues
        assert WorkflowVersion.query.count() == before


def test_metadata_json_for_a_non_mapping_document_is_none(test_app):
    with test_app.app_context():
        assert WorkflowDatasetService().metadata_json_for("- just\n- a list\n") is None


def make_version(owner_id, workflow_yaml):
    meta = DSMetaData(title="Metadata workflow", description="#17 fixture", publication_type=PublicationType.NONE)
    db.session.add(meta)
    db.session.flush()
    dataset = WorkflowDataset(user_id=owner_id, ds_meta_data_id=meta.id, validation_status=ValidationStatus.DRAFT)
    db.session.add(dataset)
    db.session.flush()
    version = WorkflowVersion(workflow_dataset_id=dataset.id, manifest_json="{}", workflow_yaml=workflow_yaml)
    db.session.add(version)
    db.session.commit()
    return version


def test_validating_a_version_does_not_extract_metadata(test_app, test_client):
    with test_app.app_context():
        owner = UserRepository().create(email="metadata-l1@example.com", password="secret")
        version = make_version(owner.id, CI_WORKFLOW)

        WorkflowDatasetService().validate_l1_version(version)

        assert version.metadata_json is None


def test_validating_a_list_document_does_not_fail(test_app, test_client):
    with test_app.app_context():
        owner = UserRepository().create(email="metadata-list@example.com", password="secret")
        version = make_version(owner.id, "- just\n- a list\n")

        WorkflowDatasetService().validate_l1_version(version)

        assert version.workflow_metadata is None


def test_detail_page_shows_the_metadata_of_a_package_uploaded_through_the_route(test_client, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    test_client.post(
        "/signup/",
        data={"email": "metadata-ui@example.com", "password": "secret", "name": "Ada", "surname": "Lovelace"},
        follow_redirects=False,
    )

    upload_response = test_client.post(
        "/workflow/upload",
        data={"package": (io.BytesIO(make_zip(workflow=CI_WORKFLOW)), "workflow.zip")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload_response.status_code == 302

    response = test_client.get(upload_response.headers["Location"])

    assert response.status_code == 200
    assert "Qué hace este workflow".encode() in response.data
    assert b"pull_request" in response.data
    assert b"actions/setup-python@v5" in response.data
    assert b"windows-latest" in response.data
    assert b"no tiene metadatos" not in response.data


def test_detail_page_without_metadata_shows_the_fallback(test_app, test_client):
    with test_app.app_context():
        owner = UserRepository().create(email="metadata-legacy@example.com", password="secret")
        dataset_id = make_version(owner.id, CI_WORKFLOW).workflow_dataset_id

    response = test_client.get(f"/workflow/{dataset_id}")

    assert response.status_code == 200
    assert b"no tiene metadatos" in response.data
