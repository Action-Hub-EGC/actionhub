"""Workflow lifecycle tests (#19): draft -> validated -> published with fakenodo."""

import io
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

from app import db
from app.features.auth.repositories import UserRepository
from app.features.workflow.lifecycle import (
    InvalidTransition,
    PublicationError,
    WorkflowPublicationService,
    can_transition,
    transition,
)
from app.features.workflow.models import ValidationStatus, WorkflowDataset
from app.features.workflow.services import WorkflowDatasetService
from app.features.workflow.tests.test_package import make_zip
from fakenodo.app import create_app as create_fakenodo
from fakenodo.store import DepositionStore

pytestmark = pytest.mark.integration

DRAFT = ValidationStatus.DRAFT
VALIDATED = ValidationStatus.VALIDATED
FAILED = ValidationStatus.FAILED
PUBLISHED = ValidationStatus.PUBLISHED


# ── Transitions ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (DRAFT, VALIDATED),
        (DRAFT, FAILED),
        (FAILED, VALIDATED),
        (FAILED, FAILED),
        (VALIDATED, VALIDATED),
        (VALIDATED, FAILED),
        (VALIDATED, PUBLISHED),
    ],
)
def test_allowed_transitions(current, target):
    workflow = SimpleNamespace(validation_status=current)

    transition(workflow, target)

    assert workflow.validation_status == target


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (DRAFT, PUBLISHED),
        (FAILED, PUBLISHED),
        (PUBLISHED, PUBLISHED),
        (PUBLISHED, VALIDATED),
        (PUBLISHED, FAILED),
        (PUBLISHED, DRAFT),
        (VALIDATED, DRAFT),
        (DRAFT, "unknown"),
    ],
)
def test_forbidden_transitions(current, target):
    workflow = SimpleNamespace(validation_status=current)

    assert can_transition(current, target) is False
    with pytest.raises(InvalidTransition):
        transition(workflow, target)
    assert workflow.validation_status == current


# ── fakenodo plumbing ───────────────────────────────────────────────────


class FakenodoRequests:
    """Route ``requests`` calls from ``ZenodoService`` to an in-process fakenodo."""

    def __init__(self, client):
        self.client = client
        self.calls = []

    def _path(self, url):
        return urlparse(url).path

    def _wrap(self, response):
        return SimpleNamespace(status_code=response.status_code, json=response.get_json)

    def post(self, url, params=None, json=None, headers=None, data=None, files=None):
        path = self._path(url)
        self.calls.append(("POST", path))
        if files:
            form = dict(data or {})
            form["file"] = (files["file"], form.get("name", "file"))
            return self._wrap(self.client.post(path, data=form, content_type="multipart/form-data"))
        return self._wrap(self.client.post(path, json=json))

    def get(self, url, params=None, headers=None):
        path = self._path(url)
        self.calls.append(("GET", path))
        return self._wrap(self.client.get(path))


@pytest.fixture
def fakenodo(tmp_path, monkeypatch):
    app = create_fakenodo(DepositionStore(tmp_path / "fakenodo.sqlite3"))
    app.config["TESTING"] = True
    monkeypatch.setenv("ZENODO_API_URL", "http://fakenodo:8000/api/deposit/depositions")
    # No ``with``: keeping the fakenodo request context open would hide the ActionHub app.
    fake = FakenodoRequests(app.test_client())
    monkeypatch.setattr("app.features.zenodo.services.requests", fake)
    return SimpleNamespace(requests=fake, store=app.extensions["fakenodo_store"])


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    return tmp_path


def upload_workflow(owner):
    package = SimpleNamespace(read=lambda: make_zip({"fixtures/input.txt": "x"}))
    dataset, issues = WorkflowDatasetService().upload_package(package, owner)
    assert issues == []
    return dataset


# ── Publication ─────────────────────────────────────────────────────────


def test_publish_stores_the_fakenodo_doi(test_app, test_client, uploads, fakenodo):
    with test_app.app_context():
        owner = UserRepository().create(email="lifecycle-publish@example.com", password="secret")
        workflow = upload_workflow(owner)
        assert workflow.validation_status == VALIDATED

        doi = WorkflowPublicationService().publish(workflow)

        stored = db.session.get(WorkflowDataset, workflow.id)
        deposition_id = stored.ds_meta_data.deposition_id
        assert doi == f"10.5072/fakenodo.{deposition_id}"
        assert stored.ds_meta_data.dataset_doi == doi
        assert stored.ds_meta_data.conceptrecid == deposition_id
        assert stored.ds_meta_data.concept_doi == f"10.5072/fakenodo.concept.{deposition_id}"
        assert stored.validation_status == PUBLISHED

        version = stored.latest_dataset_version()
        assert version.doi == doi
        assert version.deposition_id == deposition_id
        assert version.published_at is not None
        assert version.workflow_version.id == stored.latest_version().id

        deposition = fakenodo.store.get(deposition_id)
        assert deposition["state"] == "done"
        assert deposition["metadata"]["title"] == "demo-workflow"
        uploaded = sorted(item["filename"] for item in deposition["files"])
        assert uploaded == sorted(["actionhub.yaml", "workflow.yml", "README.md", "LICENSE", "fixtures__input.txt"])
        assert ("POST", f"/api/deposit/depositions/{deposition_id}/actions/publish") in fakenodo.requests.calls


def test_draft_cannot_be_published(test_app, test_client, uploads, fakenodo):
    with test_app.app_context():
        owner = UserRepository().create(email="lifecycle-draft@example.com", password="secret")
        workflow = upload_workflow(owner)
        workflow.validation_status = DRAFT
        db.session.commit()

        with pytest.raises(InvalidTransition):
            WorkflowPublicationService().publish(workflow)

        assert fakenodo.requests.calls == []
        assert workflow.ds_meta_data.dataset_doi is None


def test_published_workflow_cannot_be_published_or_validated_again(test_app, test_client, uploads, fakenodo):
    with test_app.app_context():
        owner = UserRepository().create(email="lifecycle-twice@example.com", password="secret")
        workflow = upload_workflow(owner)
        doi = WorkflowPublicationService().publish(workflow)

        with pytest.raises(InvalidTransition):
            WorkflowPublicationService().publish(workflow)
        with pytest.raises(InvalidTransition):
            WorkflowDatasetService().validate_l2_version(workflow.latest_version())

        assert workflow.validation_status == PUBLISHED
        assert workflow.ds_meta_data.dataset_doi == doi


def test_failed_publication_keeps_the_workflow_validated(test_app, test_client, uploads, fakenodo, monkeypatch):
    with test_app.app_context():
        owner = UserRepository().create(email="lifecycle-fail@example.com", password="secret")
        workflow = upload_workflow(owner)

        def broken_publish(self, deposition_id):
            raise Exception("fakenodo is down")

        monkeypatch.setattr("app.features.zenodo.services.ZenodoService.publish_deposition", broken_publish)

        with pytest.raises(PublicationError) as error:
            WorkflowPublicationService().publish(workflow)

        assert "fakenodo is down" not in str(error.value)
        stored = db.session.get(WorkflowDataset, workflow.id)
        assert stored.validation_status == VALIDATED
        assert stored.ds_meta_data.dataset_doi is None
        assert stored.ds_meta_data.deposition_id is not None


def test_workflow_without_files_cannot_be_published(test_app, test_client, uploads, fakenodo):
    with test_app.app_context():
        owner = UserRepository().create(email="lifecycle-empty@example.com", password="secret")
        workflow = upload_workflow(owner)
        for hubfile in list(workflow.latest_version().files):
            db.session.delete(hubfile)
        db.session.commit()

        with pytest.raises(PublicationError):
            WorkflowPublicationService().publish(workflow)

        assert fakenodo.requests.calls == []
        assert workflow.validation_status == VALIDATED


# ── Route ───────────────────────────────────────────────────────────────


def signup(client, email):
    client.post(
        "/signup/",
        data={"email": email, "password": "secret", "name": "Ada", "surname": "Lovelace"},
        follow_redirects=False,
    )


def upload_through_route(client):
    response = client.post(
        "/workflow/upload",
        data={"package": (io.BytesIO(make_zip()), "workflow.zip")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert response.status_code == 302
    return int(response.headers["Location"].rstrip("/").split("/")[-1])


def test_owner_publishes_from_the_detail_page(test_client, uploads, fakenodo):
    signup(test_client, "lifecycle-route@example.com")
    dataset_id = upload_through_route(test_client)

    detail = test_client.get(f"/workflow/{dataset_id}")
    assert b"Publicar con DOI" in detail.data

    response = test_client.post(f"/workflow/{dataset_id}/publish", follow_redirects=True)

    assert response.status_code == 200
    assert b"10.5072/fakenodo." in response.data
    assert b"published" in response.data
    assert b"Publicar con DOI" not in response.data


def test_publishing_twice_shows_an_error(test_client, uploads, fakenodo):
    signup(test_client, "lifecycle-route-twice@example.com")
    dataset_id = upload_through_route(test_client)
    test_client.post(f"/workflow/{dataset_id}/publish")

    response = test_client.post(f"/workflow/{dataset_id}/publish", follow_redirects=True)

    assert "No se puede pasar de &#39;published&#39; a &#39;published&#39;".encode() in response.data


def test_only_the_owner_can_publish(test_client, uploads, fakenodo):
    signup(test_client, "lifecycle-owner@example.com")
    dataset_id = upload_through_route(test_client)
    test_client.get("/logout", follow_redirects=True)
    signup(test_client, "lifecycle-intruder@example.com")

    response = test_client.post(f"/workflow/{dataset_id}/publish")

    assert response.status_code == 403
    assert fakenodo.requests.calls == []


def test_anonymous_visitors_are_sent_to_login(test_client, uploads, fakenodo):
    response = test_client.post("/workflow/1/publish", follow_redirects=False)

    assert response.status_code == 302
    assert "login" in response.headers["Location"]


def test_publish_without_doi_from_zenodo_raises_and_stays_validated(
    test_app, test_client, uploads, fakenodo, monkeypatch
):
    with test_app.app_context():
        owner = UserRepository().create(email="lifecycle-nodoi@example.com", password="secret")
        workflow = upload_workflow(owner)
        monkeypatch.setattr(
            "app.features.zenodo.services.ZenodoService.get_deposition",
            lambda self, deposition_id: {"id": deposition_id, "state": "done"},
        )

        with pytest.raises(PublicationError, match="sin DOI"):
            WorkflowPublicationService().publish(workflow)

        stored = db.session.get(WorkflowDataset, workflow.id)
        assert stored.validation_status == VALIDATED
        assert stored.ds_meta_data.dataset_doi is None
