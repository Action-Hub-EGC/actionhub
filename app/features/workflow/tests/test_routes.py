"""HTTP tests for the workflow feature scaffold (#13)."""

from datetime import datetime

import pytest

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import DSMetaData, PublicationType
from app.features.hubfile.models import Hubfile
from app.features.workflow.models import WorkflowDataset, WorkflowVersion

pytestmark = pytest.mark.integration


def make_user(email="workflow-owner@example.com"):
    return UserRepository().create(email=email, password="secret")


def make_workflow(owner_id, title="Demo workflow"):
    meta = DSMetaData(
        title=title,
        description="Workflow de ejemplo",
        publication_type=PublicationType.NONE,
    )
    db.session.add(meta)
    db.session.flush()
    dataset = WorkflowDataset(
        user_id=owner_id,
        ds_meta_data_id=meta.id,
        validation_status="validated",
        security_score=90,
        grade="A",
        created_at=datetime(2024, 1, 1, 12, 0, 0),
    )
    db.session.add(dataset)
    db.session.commit()
    return dataset


def test_health_reports_the_feature(test_client):
    response = test_client.get("/workflow/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "feature": "workflow"}


def test_index_renders(test_client):
    response = test_client.get("/workflow")

    assert response.status_code == 200
    assert b"Workflows" in response.data


def test_index_lists_a_workflow(test_client):
    with test_client.application.app_context():
        make_workflow(make_user().id, title="Release workflow")

    response = test_client.get("/workflow")

    assert response.status_code == 200
    assert b"Release workflow" in response.data
    assert b"validated" in response.data


def test_upload_redirects_anonymous_visitors_to_login(test_client):
    response = test_client.get("/workflow/upload", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_upload_renders_for_authenticated_users(test_client):
    test_client.post(
        "/signup/",
        data={"email": "workflow-upload@example.com", "password": "secret", "name": "Ada", "surname": "Lovelace"},
        follow_redirects=False,
    )

    response = test_client.get("/workflow/upload")

    assert response.status_code == 200
    assert b"Subir" in response.data
    assert b"actionhub.yaml" in response.data


def test_detail_returns_404_for_unknown_or_non_workflow_ids(test_client):
    assert test_client.get("/workflow/9999").status_code == 404


def test_detail_renders_versions_and_files(test_client):
    with test_client.application.app_context():
        workflow = make_workflow(make_user("workflow-detail@example.com").id, title="Detail workflow")
        version = WorkflowVersion(
            workflow_dataset_id=workflow.id,
            manifest_json='{"name": "detail"}',
            workflow_yaml="name: detail\non: push\njobs: {}\n",
            created_at=datetime(2024, 1, 2, 12, 0, 0),
        )
        db.session.add(version)
        db.session.flush()
        db.session.add(
            Hubfile(
                name="actionhub.yaml",
                checksum="abc",
                size=10,
                workflow_version_id=version.id,
            )
        )
        db.session.commit()
        workflow_id = workflow.id

    response = test_client.get(f"/workflow/{workflow_id}")

    assert response.status_code == 200
    assert b"Detail workflow" in response.data
    assert b"Versiones" in response.data
    assert b"actionhub.yaml" not in response.data
    assert b"1 archivos" in response.data
