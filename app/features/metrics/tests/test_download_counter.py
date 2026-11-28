"""Download counter tests: increment, API exposure and unique-download rule (#71)."""

from types import SimpleNamespace

import pytest

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.services import DSDownloadRecordService
from app.features.dataset.tests.test_integration import _make_dataset, _signup
from app.features.metrics.services import DatasetCounterService
from app.features.workflow.services import WorkflowDatasetService
from app.features.workflow.tests.test_package import make_zip


@pytest.mark.service
def test_unique_download_rule_counts_once_per_user_browser_and_dataset(test_app, clean_database):
    with test_app.app_context():
        owner = UserRepository().create(email="counter-rule@example.com", password="secret")
        first = _make_dataset(owner.id, title="First", doi="10.1234/rule-first")
        second = _make_dataset(owner.id, title="Second", doi="10.1234/rule-second")

        anonymous = SimpleNamespace(is_authenticated=False)
        authenticated = SimpleNamespace(is_authenticated=True, id=owner.id)
        downloads = DSDownloadRecordService()
        counters = DatasetCounterService()

        assert downloads.record_download(anonymous, first.id, "cookie-a") is True
        assert downloads.record_download(anonymous, first.id, "cookie-a") is False
        assert counters.counts(first.id)["downloads"] == 1

        assert downloads.record_download(anonymous, first.id, "cookie-b") is True
        assert counters.counts(first.id)["downloads"] == 2

        assert downloads.record_download(authenticated, first.id, "cookie-a") is True
        assert downloads.record_download(authenticated, first.id, "cookie-a") is False
        assert counters.counts(first.id)["downloads"] == 3

        assert downloads.record_download(authenticated, second.id, "cookie-a") is True
        assert counters.counts(first.id)["downloads"] == 3
        assert counters.counts(second.id)["downloads"] == 1


@pytest.mark.integration
def test_uvl_download_counter_increases_and_appears_in_api_and_explore(test_app, clean_database, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    with test_app.app_context():
        owner = UserRepository().create(email="counter-api-owner@example.com", password="secret")
        target = _make_dataset(owner.id, title="Tracked UVL", doi="10.1234/tracked-uvl")
        untouched = _make_dataset(owner.id, title="Untouched UVL", doi="10.1234/untouched-uvl")
        target_id = target.id
        untouched_id = untouched.id

    with test_app.test_client() as browser_a, test_app.test_client() as browser_b:
        before_single = browser_a.get(f"/api/v1/datasets/{target_id}").get_json()
        assert before_single["counts"] == {"downloads": 0, "views": 0}

        assert browser_a.get(f"/dataset/download/{target_id}").status_code == 200
        assert browser_a.get(f"/dataset/download/{target_id}").status_code == 200
        assert browser_a.get(f"/api/v1/datasets/{target_id}").get_json()["counts"]["downloads"] == 1

        _signup(browser_a, email="counter-browser-a@example.com")
        assert browser_a.get(f"/dataset/download/{target_id}").status_code == 200
        assert browser_a.get(f"/dataset/download/{target_id}").status_code == 200
        assert browser_a.get(f"/api/v1/datasets/{target_id}").get_json()["counts"]["downloads"] == 2

        assert browser_b.get(f"/dataset/download/{target_id}").status_code == 200

        single = browser_b.get(f"/api/v1/datasets/{target_id}").get_json()
        listing = browser_b.get("/api/v1/datasets/").get_json()["items"]
        explore = browser_b.post("/explore", json={"query": "", "dataset_type": "uvl"}).get_json()

        assert single["counts"] == {"downloads": 3, "views": 0}
        api_counts = {item["dataset_id"]: item["counts"] for item in listing}
        assert api_counts[target_id] == {"downloads": 3, "views": 0}
        assert api_counts[untouched_id] == {"downloads": 0, "views": 0}

        explore_counts = {item["id"]: item["counts"] for item in explore}
        assert explore_counts[target_id] == {"downloads": 3, "views": 0}
        assert explore_counts[untouched_id] == {"downloads": 0, "views": 0}


@pytest.mark.integration
def test_workflow_download_counter_respects_unique_rule_and_appears_in_explore(
    test_app, clean_database, monkeypatch, tmp_path
):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    with test_app.app_context():
        owner = UserRepository().create(email="counter-wf-owner@example.com", password="secret")
        package = SimpleNamespace(read=lambda: make_zip({"fixtures/input.txt": "ok"}))
        workflow, issues = WorkflowDatasetService().upload_package(package, owner)
        assert issues == []
        workflow.ds_meta_data.dataset_doi = "10.1234/tracked-workflow"
        db.session.commit()
        workflow_id = workflow.id

    with test_app.test_client() as browser_a, test_app.test_client() as browser_b:
        initial = browser_a.post("/explore", json={"query": "", "dataset_type": "workflow"}).get_json()
        assert next(item for item in initial if item["id"] == workflow_id)["counts"]["downloads"] == 0

        assert browser_a.get(f"/workflow/{workflow_id}/download").status_code == 200
        assert browser_a.get(f"/workflow/{workflow_id}/download").status_code == 200
        assert browser_b.get(f"/workflow/{workflow_id}/download").status_code == 200

        after = browser_b.post("/explore", json={"query": "", "dataset_type": "workflow"}).get_json()
        assert next(item for item in after if item["id"] == workflow_id)["counts"]["downloads"] == 2

        detail_html = browser_b.get(f"/workflow/{workflow_id}").get_data(as_text=True)
        assert '<span id="workflow-downloads">2</span> descargas' in detail_html
