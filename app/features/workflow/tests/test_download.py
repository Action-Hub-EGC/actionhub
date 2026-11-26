"""Download of a workflow package as ``.zip`` (#21)."""

import io
import zipfile
from types import SimpleNamespace

import pytest

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import DSDownloadRecord
from app.features.workflow.package import PackageValidator
from app.features.workflow.services import WorkflowDatasetService
from app.features.workflow.tests.test_package import make_zip

EXTRA_FILES = {"CHANGELOG.md": "## 1.0.0\n- Primera versión.", "fixtures/input.txt": "datos de ejemplo\n"}


def uploaded_files(data: bytes) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()}


def upload(email, data):
    user = UserRepository().create(email=email, password="secret")
    workflow, issues = WorkflowDatasetService().upload_package(SimpleNamespace(read=lambda: data), user)
    assert issues == []
    return workflow


@pytest.mark.service
def test_downloaded_package_matches_the_uploaded_one(test_app, test_client, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    uploaded = make_zip(EXTRA_FILES)
    with test_app.app_context():
        workflow = upload("download-roundtrip@example.com", uploaded)

        data, filename = WorkflowDatasetService().build_package_archive(workflow)

    assert filename == "demo-workflow-1.0.0.zip"
    assert uploaded_files(data) == uploaded_files(uploaded)
    assert "fixtures/input.txt" in uploaded_files(data)
    result = PackageValidator().validate_zip(data)
    assert result.valid is True, result.issues
    assert result.manifest["name"] == "demo-workflow"


@pytest.mark.service
def test_download_prefers_the_published_version(test_app, test_client, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    with test_app.app_context():
        workflow = upload("download-published@example.com", make_zip())
        service = WorkflowDatasetService()
        draft = workflow.latest_dataset_version()

        assert service.downloadable_version(workflow) is draft.workflow_version

        draft.doi = "10.1234/workflow-download"
        db.session.commit()

        assert service.downloadable_version(workflow) is workflow.latest_published_dataset_version().workflow_version


@pytest.mark.integration
def test_download_route_returns_the_zip_and_counts_once_per_browser(test_client, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    uploaded = make_zip(EXTRA_FILES)
    with test_client.application.app_context():
        workflow_id = upload("download-route@example.com", uploaded).id

    first = test_client.get(f"/workflow/{workflow_id}/download")
    # The test client sends the download cookie back: same browser, one download.
    second = test_client.get(f"/workflow/{workflow_id}/download")

    assert first.status_code == 200
    assert first.mimetype == "application/zip"
    assert "attachment" in first.headers["Content-Disposition"]
    assert "demo-workflow-1.0.0.zip" in first.headers["Content-Disposition"]
    assert "download_cookie" in first.headers.get("Set-Cookie", "")
    assert uploaded_files(first.data) == uploaded_files(uploaded)
    assert second.status_code == 200
    with test_client.application.app_context():
        assert DSDownloadRecord.query.filter_by(dataset_id=workflow_id).count() == 1

    detail = test_client.get(f"/workflow/{workflow_id}").get_data(as_text=True)
    assert f"/workflow/{workflow_id}/download" in detail
    assert "Descargar paquete" in detail
    assert '<span id="workflow-downloads">1</span> descargas' in detail


@pytest.mark.integration
def test_download_returns_404_for_unknown_workflow(test_client):
    assert test_client.get("/workflow/9999/download").status_code == 404


@pytest.mark.integration
def test_doi_page_of_a_workflow_links_to_the_package_download(test_client, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    with test_client.application.app_context():
        workflow = upload("download-doi-page@example.com", make_zip())
        workflow.ds_meta_data.dataset_doi = "10.1234/workflow-doi-page"
        db.session.commit()
        workflow_id = workflow.id

    page = test_client.get("/doi/10.1234/workflow-doi-page/").get_data(as_text=True)

    assert f'href="/workflow/{workflow_id}/download"' in page
    assert f'href="/dataset/download/{workflow_id}"' not in page
