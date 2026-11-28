"""Coexistence and UVL no-regression tests for UVLDataset and WorkflowDataset (#22)."""

import os
from datetime import datetime
from types import SimpleNamespace

import pytest

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import (
    Author,
    BaseDataset,
    DataSet,
    DatasetVersion,
    DSMetaData,
    PublicationType,
    UVLDataset,
)
from app.features.dataset.repositories import DataSetRepository
from app.features.featuremodel.models import FeatureModel, FMMetaData
from app.features.hubfile.models import Hubfile
from app.features.hubfile.services import HubfileService
from app.features.workflow.lifecycle import WorkflowPublicationService
from app.features.workflow.models import ValidationStatus, WorkflowDataset
from app.features.workflow.services import WorkflowDatasetService
from app.features.workflow.tests.test_lifecycle import FakenodoRequests
from app.features.workflow.tests.test_package import make_zip
from fakenodo.app import create_app as create_fakenodo
from fakenodo.store import DepositionStore

UVL_CONTENT = b"features\n    Root\n        optional\n            Child\n"


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def fakenodo(tmp_path, monkeypatch):
    app = create_fakenodo(DepositionStore(tmp_path / "fakenodo.sqlite3"))
    app.config["TESTING"] = True
    monkeypatch.setenv("ZENODO_API_URL", "http://fakenodo:8000/api/deposit/depositions")
    fake = FakenodoRequests(app.test_client())
    monkeypatch.setattr("app.features.zenodo.services.requests", fake)
    return fake


def _create_published_uvl(owner, title="UVL Reference", doi="10.1234/uvl-coexist", filename="sample.uvl"):
    meta = DSMetaData(
        title=title,
        description="UVL dataset verifying no-regression alongside workflows",
        publication_type=PublicationType.NONE,
        dataset_doi=doi,
        tags="uvl, spl",
    )
    db.session.add(meta)
    db.session.flush()
    db.session.add(Author(name="Ada Lovelace", ds_meta_data_id=meta.id))

    dataset = DataSet(user_id=owner.id, ds_meta_data_id=meta.id)
    db.session.add(dataset)
    db.session.flush()

    version = DatasetVersion(
        dataset_id=dataset.id,
        number=1,
        doi=doi,
        published_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
    )
    db.session.add(version)
    db.session.flush()

    fm_meta = FMMetaData(
        uvl_filename=filename,
        title="Sample FM",
        description="UVL model",
        publication_type=PublicationType.NONE,
    )
    db.session.add(fm_meta)
    db.session.flush()

    feature_model = FeatureModel(
        data_set_id=dataset.id,
        dataset_version_id=version.id,
        fm_meta_data_id=fm_meta.id,
    )
    db.session.add(feature_model)
    db.session.flush()

    version_dir = HubfileService().version_directory(dataset, version)
    os.makedirs(version_dir, exist_ok=True)
    with open(os.path.join(version_dir, filename), "wb") as handle:
        handle.write(UVL_CONTENT)

    db.session.add(
        Hubfile(
            name=filename,
            checksum="deadbeef",
            size=len(UVL_CONTENT),
            feature_model_id=feature_model.id,
        )
    )
    db.session.commit()
    return dataset


def _create_published_workflow(owner):
    package = SimpleNamespace(read=lambda: make_zip({"fixtures/input.txt": "ok"}))
    workflow, issues = WorkflowDatasetService().upload_package(package, owner)
    assert issues == []
    assert workflow.validation_status == ValidationStatus.VALIDATED
    doi = WorkflowPublicationService().publish(workflow)
    return db.session.get(WorkflowDataset, workflow.id), doi


@pytest.mark.repository
def test_uvl_and_workflow_coexist_in_base_dataset_without_breaking_uvl_queries(
    test_app, test_client, uploads, fakenodo
):
    with test_app.app_context():
        owner = UserRepository().create(email="coexist-repo@example.com", password="secret")
        uvl = _create_published_uvl(owner, doi="10.1234/uvl-repo-1")
        workflow, wf_doi = _create_published_workflow(owner)

        loaded_uvl = db.session.get(BaseDataset, uvl.id)
        loaded_wf = db.session.get(BaseDataset, workflow.id)

        assert isinstance(loaded_uvl, UVLDataset)
        assert isinstance(loaded_wf, WorkflowDataset)
        assert loaded_uvl.type == "uvl"
        assert loaded_wf.type == "workflow"
        assert loaded_uvl.get_files_count() == 1
        assert loaded_wf.get_files_count() == 5

        synchronized = DataSetRepository().get_synchronized(owner.id)
        synchronized_ids = {item.id for item in synchronized}
        assert uvl.id in synchronized_ids
        assert workflow.id not in synchronized_ids
        assert loaded_wf.ds_meta_data.dataset_doi == wf_doi


@pytest.mark.integration
def test_common_doi_page_and_uvl_download_work_for_both_types(test_app, test_client, uploads, fakenodo):
    with test_app.app_context():
        owner = UserRepository().create(email="coexist-doi@example.com", password="secret")
        uvl = _create_published_uvl(owner, title="UVL Catalog Item", doi="10.1234/uvl-doi-1")
        workflow, wf_doi = _create_published_workflow(owner)
        uvl_id = uvl.id
        uvl_doi = uvl.ds_meta_data.dataset_doi
        workflow_id = workflow.id

    uvl_page = test_client.get(f"/doi/{uvl_doi}/")
    uvl_html = uvl_page.get_data(as_text=True)
    assert uvl_page.status_code == 200
    assert "UVL Catalog Item" in uvl_html
    assert "sample.uvl" in uvl_html
    assert "Ver detalle del workflow" not in uvl_html

    uvl_download = test_client.get(f"/dataset/download/{uvl_id}")
    assert uvl_download.status_code == 200
    assert uvl_download.mimetype == "application/zip"

    wf_page = test_client.get(f"/doi/{wf_doi}/")
    wf_html = wf_page.get_data(as_text=True)
    assert wf_page.status_code == 200
    assert "demo-workflow" in wf_html
    assert "Ver detalle del workflow" in wf_html
    assert "actions/checkout@v4" in wf_html
    assert "sample.uvl" not in wf_html

    wf_detail = test_client.get(f"/workflow/{workflow_id}")
    assert wf_detail.status_code == 200
    assert b"published" in wf_detail.data


@pytest.mark.integration
def test_explore_filters_uvl_and_workflow_independently(test_app, test_client, uploads, fakenodo):
    with test_app.app_context():
        owner = UserRepository().create(email="coexist-explore@example.com", password="secret")
        uvl = _create_published_uvl(owner, title="UVL Explorable", doi="10.1234/uvl-exp-1")
        workflow, _ = _create_published_workflow(owner)
        uvl_id, workflow_id = uvl.id, workflow.id

    all_results = test_client.post("/explore", json={"query": "", "dataset_type": "any"}).get_json()
    uvl_only = test_client.post("/explore", json={"query": "", "dataset_type": "uvl"}).get_json()
    wf_only = test_client.post("/explore", json={"query": "", "dataset_type": "workflow"}).get_json()
    wf_yaml_search = test_client.post(
        "/explore", json={"query": "actions/checkout", "dataset_type": "workflow"}
    ).get_json()

    assert {item["id"] for item in all_results} >= {uvl_id, workflow_id}
    assert all(item["type"] == "uvl" for item in uvl_only)
    assert uvl_id in {item["id"] for item in uvl_only}
    assert workflow_id not in {item["id"] for item in uvl_only}
    assert all(item["type"] == "workflow" for item in wf_only)
    assert workflow_id in {item["id"] for item in wf_only}
    assert uvl_id not in {item["id"] for item in wf_only}
    assert workflow_id in {item["id"] for item in wf_yaml_search}
