"""Major versioning end to end against a running fakenodo (#41, WI-196).

Unlike the service tests, nothing here is monkeypatched: fakenodo runs as a
real HTTP server on a free local port and ``ZenodoService`` talks to it with
``requests``, exactly as in development. Each test checks the three promises
of WI-196 for both dataset types: a new version gets a new DOI, every version
shares the concept DOI, and the old versions keep their files.
"""

import hashlib
import io
import os
import threading
import zipfile
from types import SimpleNamespace

import pytest
from werkzeug.serving import make_server

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import BaseDataset, DataSet, DatasetVersion, DSMetaData, PublicationType
from app.features.dataset.services import DataSetService
from app.features.dataset.versioning import NewVersionService, VersionError
from app.features.featuremodel.models import FeatureModel, FMMetaData
from app.features.hubfile.models import Hubfile
from app.features.hubfile.services import HubfileService
from app.features.workflow.lifecycle import WorkflowPublicationService
from app.features.workflow.services import WorkflowDatasetService
from app.features.workflow.tests.test_package import MANIFEST, WORKFLOW, make_zip
from app.features.zenodo.services import ZenodoService
from fakenodo.app import create_app as create_fakenodo
from fakenodo.store import DepositionStore

pytestmark = pytest.mark.integration

UVL = {
    1: b"features\n    Root\n        optional\n            A\n",
    2: b"features\n    Root\n        optional\n            A\n            B\n",
    3: b"features\n    Root\n        optional\n            A\n            B\n            C\n",
}


@pytest.fixture
def fakenodo_server(tmp_path, monkeypatch):
    """fakenodo listening on 127.0.0.1:<free port>, with its own SQLite store."""
    app = create_fakenodo(DepositionStore(tmp_path / "fakenodo.sqlite3"))
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setenv("ZENODO_API_URL", f"{base}/api/deposit/depositions")
    monkeypatch.delenv("ZENODO_ACCESS_TOKEN", raising=False)
    # Local traffic must not go through a corporate or CI proxy.
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    yield SimpleNamespace(url=base, store=app.extensions["fakenodo_store"])
    server.shutdown()
    thread.join(timeout=5)


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    return tmp_path


def _md5(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def _zip_contents(dataset, version) -> dict[str, bytes]:
    """Files of the download archive of ``version``, without the top folder."""
    tmp_dir, name = DataSetService().build_download_archive(dataset, version)
    with zipfile.ZipFile(os.path.join(tmp_dir, name)) as archive:
        return {info.filename.split("/", 1)[1]: archive.read(info) for info in archive.infolist() if not info.is_dir()}


def _uvl_dataset_v1(owner):
    meta = DSMetaData(title="Versioned UVL", description="UVL over HTTP", publication_type=PublicationType.NONE)
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
    feature_model.files = [Hubfile(name="model.uvl", checksum=_md5(UVL[1]), size=len(UVL[1]))]
    db.session.add(feature_model)
    db.session.commit()

    directory = HubfileService().version_directory(dataset, version)
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "model.uvl"), "wb") as handle:
        handle.write(UVL[1])

    # First publication, as DataSetService.upload_dataset does it.
    zenodo = ZenodoService()
    deposition = zenodo.create_new_deposition(dataset)
    zenodo.upload_file(dataset, deposition["id"], feature_model)
    zenodo.publish_deposition(deposition["id"])
    published = zenodo.get_deposition(deposition["id"])
    version.deposition_id, version.doi = deposition["id"], published["doi"]
    meta.deposition_id, meta.dataset_doi = deposition["id"], published["doi"]
    meta.conceptrecid, meta.concept_doi = published["conceptrecid"], published["conceptdoi"]
    db.session.commit()
    return dataset


def _workflow_v1(owner):
    package = SimpleNamespace(read=lambda: make_zip({"fixtures/input.txt": "v1"}))
    workflow, issues = WorkflowDatasetService().upload_package(package, owner)
    assert issues == []
    WorkflowPublicationService().publish(workflow)
    return workflow


def test_uvl_dataset_reaches_v3_with_one_concept_doi(test_app, test_client, uploads, fakenodo_server):
    with test_app.app_context():
        dataset = _uvl_dataset_v1(UserRepository().create(email="http-uvl@example.com", password="secret"))
        concept_doi = dataset.ds_meta_data.concept_doi
        service = NewVersionService()

        for number in (2, 3):
            draft = service.start(dataset, change_note=f"v{number}")
            service.replace_file(draft, "model.uvl", UVL[number])
            service.publish(draft)

        dataset = db.session.get(BaseDataset, dataset.id)
        versions = dataset.dataset_versions
        assert [version.number for version in versions] == [1, 2, 3]
        dois = [version.doi for version in versions]
        assert len(set(dois)) == 3 and all(dois)
        assert dataset.ds_meta_data.dataset_doi == dois[-1]
        assert dataset.ds_meta_data.concept_doi == concept_doi

        # fakenodo agrees: three published depositions of the same concept.
        remote = fakenodo_server.store.list_versions(dataset.ds_meta_data.conceptrecid)
        assert [(item["version"], item["state"]) for item in remote] == [(1, "done"), (2, "done"), (3, "done")]
        assert {item["conceptdoi"] for item in remote} == {concept_doi}
        assert [item["doi"] for item in remote] == dois

        # Every old version still downloads its own bytes.
        for version in versions:
            assert _zip_contents(dataset, version) == {"model.uvl": UVL[version.number]}


def test_workflow_v2_keeps_v1_package_and_doi(test_app, test_client, uploads, fakenodo_server):
    with test_app.app_context():
        workflow = _workflow_v1(UserRepository().create(email="http-wf@example.com", password="secret"))
        first = workflow.latest_published_dataset_version()
        first_files = _zip_contents(workflow, first)
        service = NewVersionService()

        draft = service.start(workflow)
        service.replace_file(draft, "actionhub.yaml", MANIFEST.replace("1.0.0", "2.0.0").encode())
        service.replace_file(draft, "workflow.yml", WORKFLOW.replace("@v4", "@v5").encode())
        service.replace_file(draft, "fixtures/input.txt", b"v2")
        doi = service.publish(draft)

        workflow = db.session.get(BaseDataset, workflow.id)
        first, second = workflow.dataset_versions
        assert doi == second.doi != first.doi
        assert _zip_contents(workflow, first) == first_files
        assert _zip_contents(workflow, second)["fixtures/input.txt"] == b"v2"
        assert "actions/checkout@v5" in workflow.latest_version().workflow_yaml

        old = fakenodo_server.store.get(first.deposition_id)
        new = fakenodo_server.store.get(second.deposition_id)
        assert old["doi"] == first.doi and new["doi"] == doi
        assert old["conceptdoi"] == new["conceptdoi"] == workflow.ds_meta_data.concept_doi
        assert {item["filename"] for item in new["files"]} == {
            "actionhub.yaml",
            "workflow.yml",
            "README.md",
            "LICENSE",
            "fixtures__input.txt",
        }
        assert {item["checksum"] for item in old["files"]} != {item["checksum"] for item in new["files"]}


def test_rejected_versions_never_reach_fakenodo(test_app, test_client, uploads, fakenodo_server):
    with test_app.app_context():
        owner = UserRepository().create(email="http-rejected@example.com", password="secret")
        workflow = _workflow_v1(owner)
        service = NewVersionService()
        draft = service.start(workflow)

        # Same files as v1, then a manifest that still says 1.x: both are refused locally.
        with pytest.raises(VersionError):
            service.publish(draft)
        service.replace_file(draft, "workflow.yml", WORKFLOW.replace("@v4", "@v5").encode())
        with pytest.raises(VersionError):
            service.publish(draft)

        remote = fakenodo_server.store.list_versions(workflow.ds_meta_data.conceptrecid)
        assert [item["version"] for item in remote] == [1]
        assert db.session.get(DatasetVersion, draft.id).deposition_id is None


def test_download_route_serves_the_latest_published_version(test_app, test_client, uploads, fakenodo_server):
    with test_app.app_context():
        dataset = _uvl_dataset_v1(UserRepository().create(email="http-route@example.com", password="secret"))
        service = NewVersionService()
        draft = service.start(dataset)
        service.replace_file(draft, "model.uvl", UVL[2])
        dataset_id = dataset.id

        def downloaded():
            response = test_client.get(f"/dataset/download/{dataset_id}")
            assert response.status_code == 200
            with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
                return [archive.read(name) for name in archive.namelist() if name.endswith(".uvl")]

        # The open draft is not public yet.
        assert downloaded() == [UVL[1]]
        service.publish(draft)
        assert downloaded() == [UVL[2]]
