"""HTTP integration tests for dataset via the Flask test client.

Covers the HTML routes (list / DOI landing page / unsynchronized view / temp
file endpoints) as well as the ``/api/v1/datasets`` REST resource.
"""

import io
import json
from datetime import datetime, timezone

import pytest

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import DSDownloadRecord, DSViewRecord, PublicationType
from app.features.dataset.repositories import DataSetRepository, DOIMappingRepository, DSMetaDataRepository
from app.features.featuremodel.repositories import FeatureModelRepository, FMMetaDataRepository
from app.features.hubfile.repositories import HubfileRepository
from app.features.workflow.models import WorkflowDataset, WorkflowVersion

pytestmark = pytest.mark.integration


def _signup(test_client, email="owner@example.com", password="ownerpass"):
    """Register a user through the auth blueprint; the response leaves them logged in."""
    response = test_client.post(
        "/signup/",
        data={"email": email, "password": password, "name": "Olivia", "surname": "Owner"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)
    with test_client.application.app_context():
        return UserRepository().get_by_email(email).id


def _make_dataset(user_id, title="Sample dataset", doi=None, tags="tag1,tag2"):
    meta = DSMetaDataRepository().create(
        title=title,
        description=f"Description for {title}",
        publication_type=PublicationType.DATA_MANAGEMENT_PLAN,
        dataset_doi=doi,
        deposition_id=7,
        tags=tags,
    )
    return DataSetRepository().create(
        user_id=user_id,
        ds_meta_data_id=meta.id,
        created_at=datetime.now(timezone.utc),
    )


def _attach_file(dataset, name="file1.uvl", size=2048):
    fm_meta = FMMetaDataRepository().create(
        uvl_filename=name,
        title="Feature model",
        description="A feature model",
        publication_type=PublicationType.SOFTWARE_DOCUMENTATION,
    )
    feature_model = FeatureModelRepository().create(data_set_id=dataset.id, fm_meta_data_id=fm_meta.id)
    return HubfileRepository().create(name=name, checksum="deadbeef", size=size, feature_model_id=feature_model.id)


def test_upload_page_redirects_anonymous_visitors_to_login(test_client):
    response = test_client.get("/dataset/upload", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_list_dataset_shows_only_the_logged_in_users_datasets(test_client):
    user_id = _signup(test_client)
    with test_client.application.app_context():
        stranger = UserRepository().create(email="stranger@example.com", password="pass")
        _make_dataset(user_id, title="My published dataset", doi="10.1234/mine")
        _make_dataset(user_id, title="My local dataset")
        _make_dataset(stranger.id, title="Somebody elses dataset", doi="10.1234/theirs")

    response = test_client.get("/dataset/list")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "My published dataset" in body
    assert "My local dataset" in body
    assert "Somebody elses dataset" not in body


def test_unsynchronized_dataset_page_renders_for_its_owner(test_client):
    user_id = _signup(test_client)
    with test_client.application.app_context():
        dataset_id = _make_dataset(user_id, title="Work in progress").id

    response = test_client.get(f"/dataset/unsynchronized/{dataset_id}/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Work in progress" in body
    assert "Data Management Plan" in body


def test_unsynchronized_dataset_page_404s_once_the_dataset_has_a_doi(test_client):
    user_id = _signup(test_client)
    with test_client.application.app_context():
        dataset_id = _make_dataset(user_id, title="Published", doi="10.1234/published").id

    assert test_client.get(f"/dataset/unsynchronized/{dataset_id}/").status_code == 404


def test_doi_landing_page_renders_the_dataset_and_sets_a_view_cookie(test_client):
    user_id = _signup(test_client)
    with test_client.application.app_context():
        _make_dataset(user_id, title="Findable dataset", doi="10.1234/findable")

    response = test_client.get("/doi/10.1234/findable/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Findable dataset" in body
    assert "view_cookie" in response.headers.get("Set-Cookie", "")


def test_doi_landing_page_links_to_the_configured_record_service(test_client, monkeypatch):
    monkeypatch.setenv("ZENODO_RECORD_URL", "http://localhost:8000/api/deposit/depositions")
    user_id = _signup(test_client)
    with test_client.application.app_context():
        _make_dataset(user_id, title="Linked dataset", doi="10.1234/linked")

    body = test_client.get("/doi/10.1234/linked/").get_data(as_text=True)

    assert 'href="http://localhost:8000/api/deposit/depositions/7"' in body
    assert "zenodo.org/records/7" not in body


def test_doi_landing_page_renders_the_workflow_block(test_client):
    user_id = _signup(test_client, email="workflow-page@example.com")
    with test_client.application.app_context():
        meta = DSMetaDataRepository().create(
            title="Workflow dataset",
            description="A published workflow",
            publication_type=PublicationType.NONE,
            dataset_doi="10.1234/workflow-page",
        )
        workflow = WorkflowDataset(
            user_id=user_id,
            ds_meta_data_id=meta.id,
            manifest_json="{}",
            validation_status="published",
            grade="A",
        )
        db.session.add(workflow)
        db.session.flush()
        db.session.add(
            WorkflowVersion(
                workflow_dataset_id=workflow.id,
                manifest_json="{}",
                workflow_yaml="name: demo\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n",
                metadata_json=json.dumps(
                    {
                        "name": "demo",
                        "triggers": ["push"],
                        "jobs": [],
                        "runners": ["ubuntu-latest"],
                        "actions": ["actions/checkout@v4"],
                        "reusable_workflows": [],
                    }
                ),
            )
        )
        db.session.add(DSViewRecord(dataset_id=workflow.id, view_cookie="workflow-view"))
        db.session.add(DSDownloadRecord(dataset_id=workflow.id, download_cookie="workflow-download"))
        db.session.commit()

    body = test_client.get("/doi/10.1234/workflow-page/").get_data(as_text=True)

    assert "Workflow dataset" in body
    assert "WORKFLOW" in body
    assert "Disparadores" in body
    assert "actions/checkout@v4" in body
    # The page view of this request is the second unique view.
    assert '<span id="dataset-views">2</span> views' in body
    assert '<span id="dataset-downloads">1</span> downloads' in body


def test_doi_landing_page_renders_the_uvl_block(test_client):
    user_id = _signup(test_client, email="uvl-page@example.com")
    with test_client.application.app_context():
        dataset = _make_dataset(user_id, title="UVL dataset", doi="10.1234/uvl-page")
        _attach_file(dataset, name="model.uvl")

    body = test_client.get("/doi/10.1234/uvl-page/").get_data(as_text=True)

    assert "UVL dataset" in body
    assert "UVL models" in body
    assert "model.uvl" in body


def test_doi_landing_page_renders_a_dataset_without_tags(test_client):
    user_id = _signup(test_client)
    with test_client.application.app_context():
        _make_dataset(user_id, title="Untagged dataset", doi="10.1234/untagged", tags=None)

    response = test_client.get("/doi/10.1234/untagged/")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "Untagged dataset" in body


def test_doi_landing_page_redirects_a_superseded_doi(test_client):
    user_id = _signup(test_client)
    with test_client.application.app_context():
        _make_dataset(user_id, title="Findable dataset", doi="10.5678/new")
        DOIMappingRepository().create(dataset_doi_old="10.1234/old", dataset_doi_new="10.5678/new")

    response = test_client.get("/doi/10.1234/old/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/doi/10.5678/new/")


def test_doi_landing_page_404s_for_an_unknown_doi(test_client):
    assert test_client.get("/doi/10.1234/does-not-exist/").status_code == 404


def test_upload_dataset_rejects_a_form_that_fails_validation(test_client):
    _signup(test_client)

    response = test_client.post("/dataset/upload", data={"title": "", "desc": ""})

    assert response.status_code == 400
    errors = response.get_json()["message"]
    assert "title" in errors
    assert "desc" in errors


def test_temp_file_upload_rejects_anything_that_is_not_uvl(test_client, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _signup(test_client)

    response = test_client.post(
        "/dataset/file/upload",
        data={"file": (io.BytesIO(b"not a model"), "notes.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["message"] == "No valid file"


def test_temp_uvl_file_can_be_uploaded_and_then_deleted(test_client, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _signup(test_client)

    upload = test_client.post(
        "/dataset/file/upload",
        data={"file": (io.BytesIO(b"features\n\tRoot\n"), "model.uvl")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 200
    filename = upload.get_json()["filename"]
    assert filename == "model.uvl"

    deleted = test_client.post("/dataset/file/delete", json={"file": filename})
    assert deleted.status_code == 200
    assert deleted.get_json()["message"] == "File deleted successfully"

    # The file is gone, so a second delete reports it as missing.
    missing = test_client.post("/dataset/file/delete", json={"file": filename})
    assert missing.status_code == 404
    assert missing.get_json()["error"] == "Error: File not found"


def test_temp_file_delete_redirects_anonymous_visitors_to_login(test_client):
    response = test_client.post("/dataset/file/delete", json={"file": "model.uvl"}, follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_api_lists_every_dataset_with_its_files(test_client):
    user_id = _signup(test_client)
    with test_client.application.app_context():
        first = _make_dataset(user_id, title="First dataset", doi="10.1234/first")
        file_id = _attach_file(first, name="file1.uvl", size=2048).id
        _make_dataset(user_id, title="Second dataset")

    response = test_client.get("/api/v1/datasets/")
    payload = response.get_json()

    assert response.status_code == 200
    assert {item["name"] for item in payload["items"]} == {"First dataset", "Second dataset"}

    published = next(item for item in payload["items"] if item["name"] == "First dataset")
    assert published["doi"].endswith("/doi/10.1234/first")
    assert published["files"] == [{"file_id": file_id, "file_name": "file1.uvl", "size": "2.0 KB"}]
    assert "created" in published


def test_api_returns_a_single_dataset_or_404(test_client):
    user_id = _signup(test_client)
    with test_client.application.app_context():
        dataset_id = _make_dataset(user_id, title="Only dataset", doi="10.1234/only").id

    found = test_client.get(f"/api/v1/datasets/{dataset_id}")
    assert found.status_code == 200
    assert found.get_json()["dataset_id"] == dataset_id
    assert found.get_json()["name"] == "Only dataset"
    assert found.get_json()["files"] == []

    missing = test_client.get(f"/api/v1/datasets/{dataset_id + 999}")
    assert missing.status_code == 404
    assert missing.get_json()["message"] == "DataSet not found"


# --- Per-dataset counts (#67) ---


def test_dataset_page_shows_unique_views_and_downloads(test_client, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))  # The zip of a dataset without files is empty.
    user_id = _signup(test_client)
    with test_client.application.app_context():
        dataset_id = _make_dataset(user_id, title="Counted", doi="10.1234/counted").id

    # The test client keeps the cookies: the second download and view are the
    # same browser and must not count again.
    for _ in range(2):
        assert test_client.get(f"/dataset/download/{dataset_id}").status_code == 200
    test_client.get("/doi/10.1234/counted/")
    body = test_client.get("/doi/10.1234/counted/").get_data(as_text=True)

    assert '<span id="dataset-views">1</span> views' in body
    assert '<span id="dataset-downloads">1</span> downloads' in body
    assert "repeated clicks are not counted" in body


def test_api_includes_the_counts_of_each_dataset(test_client, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    user_id = _signup(test_client)
    with test_client.application.app_context():
        downloaded = _make_dataset(user_id, title="Downloaded", doi="10.1234/downloaded").id
        untouched = _make_dataset(user_id, title="Untouched").id
    test_client.get(f"/dataset/download/{downloaded}")

    listing = test_client.get("/api/v1/datasets/").get_json()["items"]
    single = test_client.get(f"/api/v1/datasets/{downloaded}").get_json()

    counts = {item["dataset_id"]: item["counts"] for item in listing}
    assert counts == {
        downloaded: {"downloads": 1, "views": 0},
        untouched: {"downloads": 0, "views": 0},
    }
    assert single["counts"] == {"downloads": 1, "views": 0}
