"""Model tests for WorkflowDataset and WorkflowVersion (#12)."""

from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import BaseDataset, DSMetaData, PublicationType
from app.features.featuremodel.models import FeatureModel
from app.features.hubfile.models import Hubfile
from app.features.workflow.models import WorkflowDataset, WorkflowVersion

pytestmark = pytest.mark.repository


def make_user(email):
    return UserRepository().create(email=email, password="secret")


def make_meta(title):
    meta = DSMetaData(
        title=title,
        description=f"Description for {title}",
        publication_type=PublicationType.NONE,
    )
    db.session.add(meta)
    db.session.flush()
    return meta


def make_workflow(owner_id, title="workflow"):
    dataset = WorkflowDataset(
        user_id=owner_id,
        ds_meta_data_id=make_meta(title).id,
        manifest_json='{"name": "demo"}',
        validation_status="validated",
        security_score=92,
        grade="A",
        actionlint_version="1.7.7",
        package_format="zip",
    )
    db.session.add(dataset)
    db.session.flush()
    return dataset


def make_version(dataset_id, created_at=datetime(2024, 1, 1, 12, 0, 0)):
    version = WorkflowVersion(
        workflow_dataset_id=dataset_id,
        manifest_json='{"name": "demo", "version": "1.0.0"}',
        workflow_yaml="name: demo\non: push\njobs: {}\n",
        created_at=created_at,
    )
    db.session.add(version)
    db.session.flush()
    return version


def test_workflow_dataset_is_loaded_through_base_dataset(test_app, test_client):
    with test_app.app_context():
        owner = make_user("workflow-polymorphic@example.com")
        dataset = make_workflow(owner.id)
        db.session.commit()

        loaded = db.session.get(BaseDataset, dataset.id)

        assert isinstance(loaded, WorkflowDataset)
        assert loaded.type == "workflow"
        assert loaded.validation_status == "validated"
        assert loaded.security_score == 92
        assert loaded.grade == "A"


def test_workflow_versions_and_files_are_aggregated(test_app, test_client):
    with test_app.app_context():
        owner = make_user("workflow-files@example.com")
        dataset = make_workflow(owner.id)
        version = make_version(dataset.id)
        db.session.add(
            Hubfile(
                name="actionhub.yaml",
                checksum="abc",
                size=100,
                workflow_version_id=version.id,
            )
        )
        db.session.commit()

        loaded = db.session.get(BaseDataset, dataset.id)

        assert len(loaded.versions) == 1
        assert loaded.latest_version().id == version.id
        assert loaded.get_files_count() == 1
        assert loaded.get_file_total_size() == 100
        assert [file.name for file in loaded.files()] == ["actionhub.yaml"]

        with test_app.test_request_context("/"):
            payload = loaded.to_dict()
        assert payload["files_count"] == 1
        assert payload["files"][0]["name"] == "actionhub.yaml"


def test_file_cannot_belong_to_both_version_types(test_app, test_client):
    with test_app.app_context():
        owner = make_user("workflow-constraint@example.com")
        dataset = make_workflow(owner.id)
        version = make_version(dataset.id)
        feature_model = FeatureModel(data_set_id=dataset.id)
        db.session.add(feature_model)
        db.session.flush()
        db.session.add(
            Hubfile(
                name="both.yaml",
                checksum="abc",
                size=1,
                workflow_version_id=version.id,
                feature_model_id=feature_model.id,
            )
        )

        with pytest.raises((IntegrityError, OperationalError)):
            db.session.commit()
        db.session.rollback()


def test_file_must_belong_to_one_version_type(test_app, test_client):
    with test_app.app_context():
        db.session.add(Hubfile(name="orphan.yaml", checksum="abc", size=1))

        # MariaDB reports a CHECK violation as error 4025, which PyMySQL maps
        # to OperationalError rather than IntegrityError.
        with pytest.raises((IntegrityError, OperationalError), match="ck_file_one_version"):
            db.session.commit()
        db.session.rollback()
