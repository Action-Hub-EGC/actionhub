"""New major version of a published dataset against fakenodo (#38)."""

import hashlib
import os
from types import SimpleNamespace

import pytest

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import BaseDataset, DataSet, DatasetVersion, DSMetaData, PublicationType
from app.features.dataset.versioning import NewVersionService, VersionError, VersionPublicationError
from app.features.featuremodel.models import FeatureModel, FMMetaData
from app.features.hubfile.models import Hubfile
from app.features.hubfile.services import HubfileService
from app.features.workflow.lifecycle import WorkflowPublicationService
from app.features.workflow.models import ValidationStatus
from app.features.workflow.services import WorkflowDatasetService
from app.features.workflow.tests.test_lifecycle import FakenodoRequests
from app.features.workflow.tests.test_package import MANIFEST, WORKFLOW, make_zip
from app.features.zenodo.services import ZenodoService
from fakenodo.app import create_app as create_fakenodo
from fakenodo.store import DepositionStore

pytestmark = pytest.mark.integration

UVL_V1 = b"features\n    Root\n        optional\n            A\n"
UVL_V2 = b"features\n    Root\n        optional\n            A\n            B\n"


class VersionedFakenodoRequests(FakenodoRequests):
    """``FakenodoRequests`` plus ``DELETE``, used to replace the files of a draft."""

    def delete(self, url, params=None, headers=None):
        path = self._path(url)
        self.calls.append(("DELETE", path))
        return self._wrap(self.client.delete(path))


@pytest.fixture
def fakenodo(tmp_path, monkeypatch):
    app = create_fakenodo(DepositionStore(tmp_path / "fakenodo.sqlite3"))
    app.config["TESTING"] = True
    monkeypatch.setenv("ZENODO_API_URL", "http://fakenodo:8000/api/deposit/depositions")
    fake = VersionedFakenodoRequests(app.test_client())
    monkeypatch.setattr("app.features.zenodo.services.requests", fake)
    return SimpleNamespace(requests=fake, store=app.extensions["fakenodo_store"])


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    return tmp_path


def _owner(email):
    return UserRepository().create(email=email, password="secret")


def _md5(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def published_uvl_dataset(owner):
    """A UVL dataset whose v1 (``model.uvl``) is published in fakenodo."""
    meta = DSMetaData(title="UVL with versions", description="desc", publication_type=PublicationType.NONE)
    db.session.add(meta)
    db.session.flush()
    dataset = DataSet(user_id=owner.id, ds_meta_data_id=meta.id)
    db.session.add(dataset)
    db.session.flush()
    version = DatasetVersion(dataset_id=dataset.id, number=1)
    db.session.add(version)
    db.session.flush()
    fm_meta = FMMetaData(uvl_filename="model.uvl", title="Model", description="", publication_type=PublicationType.NONE)
    feature_model = FeatureModel(data_set_id=dataset.id, dataset_version_id=version.id, fm_meta_data=fm_meta)
    feature_model.files = [Hubfile(name="model.uvl", checksum=_md5(UVL_V1), size=len(UVL_V1))]
    db.session.add(feature_model)
    db.session.commit()

    directory = HubfileService().version_directory(dataset, version)
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "model.uvl"), "wb") as handle:
        handle.write(UVL_V1)

    zenodo = ZenodoService()
    deposition = zenodo.create_new_deposition(dataset)
    zenodo.upload_file(dataset, deposition["id"], feature_model)
    zenodo.publish_deposition(deposition["id"])
    published = zenodo.get_deposition(deposition["id"])
    version.deposition_id = deposition["id"]
    version.doi = published["doi"]
    meta.deposition_id = deposition["id"]
    meta.dataset_doi = published["doi"]
    meta.conceptrecid = deposition["conceptrecid"]
    meta.concept_doi = published["conceptdoi"]
    db.session.commit()
    return dataset


def published_workflow(owner):
    package = SimpleNamespace(read=lambda: make_zip({"fixtures/input.txt": "x"}))
    workflow, issues = WorkflowDatasetService().upload_package(package, owner)
    assert issues == []
    WorkflowPublicationService().publish(workflow)
    return workflow


# ── UVL ─────────────────────────────────────────────────────────────────


def test_uvl_new_version_gets_a_new_doi_and_keeps_the_old_files(test_app, test_client, uploads, fakenodo):
    with test_app.app_context():
        dataset = published_uvl_dataset(_owner("uvl-v2@example.com"))
        first = dataset.latest_published_dataset_version()
        first_doi, concept_doi = first.doi, dataset.ds_meta_data.concept_doi
        service = NewVersionService()

        draft = service.start(dataset, change_note="Adds feature B")
        service.replace_file(draft, "model.uvl", UVL_V2)
        service.add_file(draft, "extra.uvl", UVL_V1, title="Extra model")
        doi = service.publish(draft)

        dataset = db.session.get(BaseDataset, dataset.id)
        second = dataset.latest_published_dataset_version()
        assert second.number == 2 and second.doi == doi != first_doi
        assert second.change_note == "Adds feature B"
        assert dataset.ds_meta_data.dataset_doi == doi
        assert dataset.ds_meta_data.concept_doi == concept_doi

        # The old version keeps its files and DOI, on disk and in fakenodo.
        hubfiles = HubfileService()
        old_path = os.path.join(hubfiles.read_directory(dataset, first), "model.uvl")
        assert open(old_path, "rb").read() == UVL_V1
        assert [file.name for file in first.files()] == ["model.uvl"]
        assert first.doi == first_doi
        assert sorted(file.name for file in second.files()) == ["extra.uvl", "model.uvl"]

        old, new = fakenodo.store.get(first.deposition_id), fakenodo.store.get(second.deposition_id)
        assert old["conceptdoi"] == new["conceptdoi"] == concept_doi
        assert old["doi"] == first_doi and new["doi"] == doi
        assert [file["filename"] for file in old["files"]] == ["model.uvl"]
        assert sorted(file["filename"] for file in new["files"]) == ["extra.uvl", "model.uvl"]

        # Visitors see the current version only, never both.
        assert sorted(file.name for file in dataset.files()) == ["extra.uvl", "model.uvl"]
        assert len(dataset.current_feature_models()) == 2


def test_invalid_uvl_is_rejected_and_the_draft_is_unchanged(test_app, test_client, uploads, fakenodo):
    with test_app.app_context():
        dataset = published_uvl_dataset(_owner("uvl-bad@example.com"))
        service = NewVersionService()
        draft = service.start(dataset)

        with pytest.raises(VersionError) as error:
            service.replace_file(draft, "model.uvl", b"features\n    Root {{{\n")
        assert error.value.issues

        path = HubfileService().get_path_by_hubfile(draft.files()[0])
        assert open(path, "rb").read() == UVL_V1
        with pytest.raises(VersionError):
            service.add_file(draft, "notes.txt", b"hello")
        with pytest.raises(VersionError):
            service.add_file(draft, "../escape.uvl", UVL_V1)


def test_a_draft_must_change_some_file_and_keep_one_model(test_app, test_client, uploads, fakenodo):
    with test_app.app_context():
        dataset = published_uvl_dataset(_owner("uvl-same@example.com"))
        service = NewVersionService()
        draft = service.start(dataset)

        with pytest.raises(VersionError, match="no cambia"):
            service.publish(draft)
        with pytest.raises(VersionError, match="al menos un modelo"):
            service.remove_file(draft, "model.uvl")

        service.add_file(draft, "extra.uvl", UVL_V2)
        service.remove_file(draft, "model.uvl")
        assert [file.name for file in draft.files()] == ["extra.uvl"]
        assert service.publish(draft)


# ── Workflow ────────────────────────────────────────────────────────────


def test_workflow_new_version_is_revalidated_and_published(test_app, test_client, uploads, fakenodo):
    with test_app.app_context():
        workflow = published_workflow(_owner("wf-v2@example.com"))
        first = workflow.latest_published_dataset_version()
        workflow.grade, workflow.security_score = "B", 80
        db.session.commit()
        service = NewVersionService()

        draft = service.start(workflow)
        new_workflow = WORKFLOW.replace("actions/checkout@v4", "actions/setup-python@v5")
        service.replace_file(draft, "workflow.yml", new_workflow.encode())
        service.replace_file(draft, "actionhub.yaml", MANIFEST.replace("1.0.0", "2.0.0").encode())
        service.add_file(draft, "CHANGELOG.md", b"## 2.0.0\n\n- New step.\n")
        service.remove_file(draft, "fixtures/input.txt")
        doi = service.publish(draft)

        workflow = db.session.get(BaseDataset, workflow.id)
        second = workflow.latest_published_dataset_version()
        assert second.number == 2 and second.doi == doi != first.doi
        assert workflow.validation_status == ValidationStatus.PUBLISHED
        assert workflow.latest_version() is second.workflow_version
        assert "setup-python" in second.workflow_version.workflow_yaml
        assert second.workflow_version.workflow_metadata["actions"] == ["actions/setup-python@v5"]
        assert '"version": "2.0.0"' in workflow.manifest_json
        # L4 (#18) does not exist yet: the grade of v1 must not describe v2.
        assert workflow.grade is None and workflow.security_score is None

        assert "actions/checkout@v4" in first.workflow_version.workflow_yaml
        assert sorted(file.name for file in first.workflow_version.files) == sorted(
            ["actionhub.yaml", "workflow.yml", "README.md", "LICENSE", "fixtures/input.txt"]
        )
        assert sorted(file.name for file in workflow.files()) == sorted(
            ["actionhub.yaml", "workflow.yml", "README.md", "LICENSE", "CHANGELOG.md"]
        )
        new = fakenodo.store.get(second.deposition_id)
        assert "fixtures__input.txt" not in [file["filename"] for file in new["files"]]
        assert new["conceptdoi"] == workflow.ds_meta_data.concept_doi


def test_workflow_version_must_pass_l1_l2_and_bump_the_manifest_major(test_app, test_client, uploads, fakenodo):
    with test_app.app_context():
        workflow = published_workflow(_owner("wf-invalid@example.com"))
        service = NewVersionService()
        draft = service.start(workflow)

        service.replace_file(draft, "workflow.yml", b"name: Broken\non: push\njobs: {}\n")
        service.replace_file(draft, "actionhub.yaml", MANIFEST.replace("1.0.0", "2.0.0").encode())
        with pytest.raises(VersionError) as error:
            service.publish(draft)
        assert error.value.issues

        service.replace_file(draft, "workflow.yml", WORKFLOW.replace("@v4", "@v5").encode())
        service.replace_file(draft, "actionhub.yaml", MANIFEST.replace("1.0.0", "1.1.0").encode())
        with pytest.raises(VersionError) as error:
            service.publish(draft)
        assert any(issue.field == "version" for issue in error.value.issues)

        assert draft.doi is None and draft.deposition_id is None
        with pytest.raises(VersionError, match="obligatorio"):
            service.remove_file(draft, "workflow.yml")


def test_failed_publication_keeps_the_draft_and_can_be_retried(test_app, test_client, uploads, fakenodo, monkeypatch):
    with test_app.app_context():
        workflow = published_workflow(_owner("wf-retry@example.com"))
        first_doi = workflow.ds_meta_data.dataset_doi
        service = NewVersionService()
        draft = service.start(workflow)
        service.replace_file(draft, "workflow.yml", WORKFLOW.replace("@v4", "@v5").encode())
        service.replace_file(draft, "actionhub.yaml", MANIFEST.replace("1.0.0", "2.0.0").encode())

        original = ZenodoService.publish_deposition
        monkeypatch.setattr(ZenodoService, "publish_deposition", lambda self, deposition_id: 1 / 0)
        with pytest.raises(VersionPublicationError):
            service.publish(draft)

        draft = db.session.get(DatasetVersion, draft.id)
        assert draft.doi is None and draft.deposition_id is not None
        assert workflow.ds_meta_data.dataset_doi == first_doi

        monkeypatch.setattr(ZenodoService, "publish_deposition", original)
        doi = service.publish(draft)
        assert doi != first_doi
        assert len(fakenodo.store.list_versions(workflow.ds_meta_data.conceptrecid)) == 2


# ── Rules ───────────────────────────────────────────────────────────────


def test_only_published_datasets_get_a_new_version_and_drafts_are_unique(test_app, test_client, uploads, fakenodo):
    with test_app.app_context():
        owner = _owner("wf-rules@example.com")
        package = SimpleNamespace(read=lambda: make_zip())
        unpublished, _ = WorkflowDatasetService().upload_package(package, owner)
        service = NewVersionService()
        with pytest.raises(VersionError, match="publicado"):
            service.start(unpublished)

        workflow = published_workflow(owner)
        draft = service.start(workflow)
        assert service.start(workflow) is draft
        assert service.draft_for(workflow) is draft
        assert workflow.latest_version() is workflow.latest_published_dataset_version().workflow_version

        published = workflow.latest_published_dataset_version()
        with pytest.raises(VersionError, match="ya está publicada"):
            service.replace_file(published, "workflow.yml", b"x")

        directory = HubfileService().version_directory(workflow, draft)
        service.discard(draft)
        assert not os.path.isdir(directory)
        assert [version.number for version in db.session.get(BaseDataset, workflow.id).dataset_versions] == [1]
