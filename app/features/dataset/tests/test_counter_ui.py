"""Counter UI on the common page for both dataset types (#68)."""

import json

import pytest

from app import db
from app.features.dataset.models import DSDownloadRecord, DSMetaData, DSViewRecord, PublicationType
from app.features.dataset.tests.test_integration import _make_dataset, _signup
from app.features.workflow.models import WorkflowDataset, WorkflowVersion

pytestmark = pytest.mark.integration


def _workflow_with_activity(user_id, doi):
    meta = DSMetaData(
        title="Counted workflow",
        description="Workflow used by the counter UI test",
        publication_type=PublicationType.NONE,
        dataset_doi=doi,
    )
    db.session.add(meta)
    db.session.flush()
    workflow = WorkflowDataset(
        user_id=user_id,
        ds_meta_data_id=meta.id,
        manifest_json="{}",
        validation_status="published",
    )
    db.session.add(workflow)
    db.session.flush()
    db.session.add(
        WorkflowVersion(
            workflow_dataset_id=workflow.id,
            manifest_json="{}",
            workflow_yaml="name: counted\non: push\n",
            metadata_json=json.dumps({"triggers": ["push"], "runners": [], "actions": [], "jobs": []}),
        )
    )
    db.session.add(DSViewRecord(dataset_id=workflow.id, view_cookie="workflow-view"))
    db.session.add(DSDownloadRecord(dataset_id=workflow.id, download_cookie="workflow-download"))
    db.session.commit()
    return workflow


def test_counts_are_rendered_and_marked_for_a_workflow_dataset(test_client):
    user_id = _signup(test_client, email="counter-workflow@example.com")
    with test_client.application.app_context():
        workflow_id = _workflow_with_activity(user_id, "10.1234/counter-workflow").id

    body = test_client.get("/doi/10.1234/counter-workflow/").get_data(as_text=True)

    assert f'data-dataset-id="{workflow_id}"' in body
    assert 'data-dataset-type="workflow"' in body
    assert '<span id="dataset-views">2</span> views' in body
    assert '<span id="dataset-downloads">1</span> downloads' in body


def test_counts_are_rendered_and_marked_for_a_uvl_dataset(test_client):
    user_id = _signup(test_client, email="counter-uvl@example.com")
    with test_client.application.app_context():
        dataset = _make_dataset(user_id, title="Counted UVL", doi="10.1234/counter-uvl")
        dataset_id = dataset.id
        db.session.add(DSViewRecord(dataset_id=dataset_id, view_cookie="uvl-view"))
        db.session.add(DSDownloadRecord(dataset_id=dataset_id, download_cookie="uvl-download"))
        db.session.commit()

    body = test_client.get("/doi/10.1234/counter-uvl/").get_data(as_text=True)

    assert f'data-dataset-id="{dataset_id}"' in body
    assert 'data-dataset-type="uvl"' in body
    assert '<span id="dataset-views">2</span> views' in body
    assert '<span id="dataset-downloads">1</span> downloads' in body
