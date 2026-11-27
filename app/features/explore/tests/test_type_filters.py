"""Type-specific filters for UVL and workflow datasets (#52)."""

import json
from datetime import datetime

import pytest

from app import db
from app.features.auth.models import User
from app.features.dataset.models import DataSet, DSMetaData, DSMetrics, PublicationType
from app.features.explore.filters import filters_for
from app.features.explore.repositories import ExploreRepository
from app.features.workflow.models import WorkflowDataset, WorkflowVersion

pytestmark = pytest.mark.repository


def _owner():
    user = User.query.filter_by(email="filters-owner@example.com").first()
    if user is None:
        user = User(email="filters-owner@example.com")
        user.set_password("ownerpass")
        db.session.add(user)
        db.session.flush()
    return user


def _uvl(title, models, features, created_at):
    metrics = DSMetrics(number_of_models=str(models), number_of_features=str(features))
    db.session.add(metrics)
    db.session.flush()
    meta = DSMetaData(
        title=title,
        description=f"{title} description",
        publication_type=PublicationType.NONE,
        dataset_doi=f"10.1234/{title.lower().replace(' ', '-')}",
        ds_metrics_id=metrics.id,
    )
    db.session.add(meta)
    db.session.flush()
    dataset = DataSet(user_id=_owner().id, ds_meta_data_id=meta.id, created_at=created_at)
    db.session.add(dataset)
    db.session.commit()
    return dataset


def _workflow(title, grade, trigger, runner, action, created_at):
    meta = DSMetaData(
        title=title,
        description=f"{title} description",
        publication_type=PublicationType.NONE,
        dataset_doi=f"10.1234/{title.lower().replace(' ', '-')}",
    )
    db.session.add(meta)
    db.session.flush()
    workflow = WorkflowDataset(
        user_id=_owner().id,
        ds_meta_data_id=meta.id,
        created_at=created_at,
        manifest_json="{}",
        validation_status="published",
        grade=grade,
    )
    db.session.add(workflow)
    db.session.flush()
    db.session.add(
        WorkflowVersion(
            workflow_dataset_id=workflow.id,
            manifest_json="{}",
            workflow_yaml=f"name: {title}\non: {trigger}\n",
            metadata_json=json.dumps(
                {
                    "name": title,
                    "triggers": [trigger],
                    "jobs": [],
                    "runners": [runner],
                    "actions": [action],
                    "reusable_workflows": [],
                }
            ),
        )
    )
    db.session.commit()
    return workflow


def _titles(datasets):
    return [dataset.ds_meta_data.title for dataset in datasets]


def test_filters_are_registered_per_dataset_type(test_app):
    assert {item.name for item in filters_for("uvl")} == {
        "models_min",
        "models_max",
        "features_min",
        "features_max",
    }
    assert {item.name for item in filters_for("workflow")} == {"grade", "trigger", "runner", "action"}


def test_uvl_filters_by_number_of_models_and_features(test_app, clean_database):
    with test_app.app_context():
        _uvl("Small model", models=2, features=5, created_at=datetime(2024, 1, 1))
        _uvl("Large model", models=8, features=40, created_at=datetime(2024, 2, 1))
        repository = ExploreRepository()

        assert _titles(repository.filter("", models_min=3)) == ["Large model"]
        assert _titles(repository.filter("", models_max=3)) == ["Small model"]
        assert _titles(repository.filter("", features_min=10)) == ["Large model"]
        assert _titles(repository.filter("", features_max=10)) == ["Small model"]
        assert _titles(repository.filter("", models_min=3, features_max=10)) == []


def test_workflow_filters_by_grade_trigger_runner_and_action(test_app, clean_database):
    with test_app.app_context():
        _workflow("Push pipeline", "A", "push", "ubuntu-latest", "actions/checkout@v4", datetime(2024, 1, 1))
        _workflow("PR pipeline", "B", "pull_request", "windows-latest", "actions/setup-python@v5", datetime(2024, 2, 1))
        repository = ExploreRepository()

        assert _titles(repository.filter("", grade="A")) == ["Push pipeline"]
        assert _titles(repository.filter("", trigger="pull_request")) == ["PR pipeline"]
        assert _titles(repository.filter("", runner="windows-latest")) == ["PR pipeline"]
        assert _titles(repository.filter("", action="actions/checkout@v4")) == ["Push pipeline"]
        assert _titles(repository.filter("", grade="A", runner="windows-latest")) == []


def test_type_filters_combine_with_dataset_type(test_app, clean_database):
    with test_app.app_context():
        _uvl("UVL candidate", models=5, features=20, created_at=datetime(2024, 1, 1))
        _workflow("Workflow candidate", "A", "push", "ubuntu-latest", "actions/checkout@v4", datetime(2024, 2, 1))
        repository = ExploreRepository()

        assert _titles(repository.filter("", dataset_type="uvl", models_min=1)) == ["UVL candidate"]
        assert _titles(repository.filter("", dataset_type="workflow", grade="A")) == ["Workflow candidate"]
        # A filter of the other type is ignored instead of hiding every result.
        assert _titles(repository.filter("", dataset_type="workflow", models_min=1)) == ["Workflow candidate"]
        assert _titles(repository.filter("", dataset_type="uvl", grade="A")) == ["UVL candidate"]


def test_explore_form_renders_the_registered_filters(test_client):
    body = test_client.get("/explore").get_data(as_text=True)

    assert 'id="filter_models_min"' in body
    assert 'id="filter_features_max"' in body
    assert 'id="filter_grade"' in body
    assert 'id="filter_trigger"' in body
    assert 'data-explore-filter="models_min"' in body
    assert 'data-explore-filter="grade"' in body
