"""Contract tests running ActionHub's ZenodoService against fakenodo over HTTP."""

import hashlib
import threading

import pytest
from werkzeug.serving import make_server

from app import db
from app.features.auth.models import User
from app.features.dataset.models import Author, DataSet, DSMetaData, PublicationType
from app.features.featuremodel.models import FeatureModel, FMMetaData
from app.features.zenodo.services import ZenodoService
from fakenodo.app import create_app
from fakenodo.store import DepositionStore

pytestmark = pytest.mark.integration


@pytest.fixture
def fakenodo_url(tmp_path, monkeypatch):
    app = create_app(DepositionStore(tmp_path / "fakenodo.sqlite3"))
    server = make_server("127.0.0.1", 0, app)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{server.server_port}/api/deposit/depositions"
    monkeypatch.setenv("ZENODO_API_URL", url)
    monkeypatch.delenv("ZENODO_ACCESS_TOKEN", raising=False)
    try:
        yield url
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _create_dataset_with_model(email, tmp_path, filename="model.uvl", content=b"features\n    Root\n"):
    user = User(email=email, password="ownerpass")
    db.session.add(user)
    db.session.commit()

    meta_data = DSMetaData(
        title="Contract dataset",
        description="Dataset used to verify ZenodoService against fakenodo",
        publication_type=PublicationType.JOURNAL_ARTICLE,
        tags="ci, workflow",
    )
    db.session.add(meta_data)
    db.session.commit()

    author = Author(name="Jane Doe", affiliation="US", orcid="0000-0001-2345-6789", ds_meta_data_id=meta_data.id)
    db.session.add(author)
    db.session.commit()

    dataset = DataSet(user_id=user.id, ds_meta_data_id=meta_data.id)
    db.session.add(dataset)
    db.session.commit()

    fm_meta_data = FMMetaData(
        uvl_filename=filename,
        title="Contract model",
        description="Feature model uploaded in contract test",
        publication_type=PublicationType.NONE,
    )
    db.session.add(fm_meta_data)
    db.session.commit()

    feature_model = FeatureModel(data_set_id=dataset.id, fm_meta_data_id=fm_meta_data.id)
    db.session.add(feature_model)
    db.session.commit()

    file_dir = tmp_path / f"user_{user.id}" / f"dataset_{dataset.id}"
    file_dir.mkdir(parents=True, exist_ok=True)
    (file_dir / filename).write_bytes(content)

    return user, dataset, feature_model


def test_zenodo_service_connection_and_probe_against_fakenodo(test_app, fakenodo_url, tmp_path, monkeypatch):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))

    with test_app.app_context():
        service = ZenodoService()
        assert service.ZENODO_API_URL == fakenodo_url
        assert service.test_connection() is True
        assert service.get_all_depositions() == []

    with test_app.test_client() as client:
        response = client.get("/zenodo/test")

    assert response.status_code == 200
    assert response.get_json() == {"success": True, "messages": []}
    assert not (tmp_path / "test_file.txt").exists()
    with test_app.app_context():
        assert ZenodoService().get_all_depositions() == []


def test_zenodo_service_publish_flow_against_fakenodo(test_app, clean_database, fakenodo_url, tmp_path, monkeypatch):
    content = b"features\n    Root\n"
    monkeypatch.setattr("app.features.zenodo.services.uploads_folder_name", lambda: str(tmp_path))

    with test_app.app_context():
        user, dataset, feature_model = _create_dataset_with_model(
            "contract-happy@example.com",
            tmp_path,
            filename="model.uvl",
            content=content,
        )
        service = ZenodoService()

        created = service.create_new_deposition(dataset)
        deposition_id = created["id"]
        assert created["conceptrecid"] == deposition_id
        assert created["state"] == "unsubmitted"
        assert created["doi"] is None
        assert created["metadata"]["title"] == "Contract dataset"
        assert created["metadata"]["upload_type"] == "publication"
        assert created["metadata"]["publication_type"] == "article"
        assert created["metadata"]["keywords"] == ["ci", "workflow", "uvlhub"]
        assert created["metadata"]["creators"] == [
            {"name": "Jane Doe", "affiliation": "US", "orcid": "0000-0001-2345-6789"}
        ]

        listed = service.get_all_depositions()
        assert [item["id"] for item in listed] == [deposition_id]

        uploaded = service.upload_file(dataset, deposition_id, feature_model, user=user)
        assert uploaded == {
            "id": 1,
            "filename": "model.uvl",
            "filesize": len(content),
            "checksum": f"md5:{hashlib.md5(content).hexdigest()}",
        }

        published = service.publish_deposition(deposition_id)
        expected_doi = f"10.5072/fakenodo.{deposition_id}"
        expected_concept_doi = f"10.5072/fakenodo.concept.{deposition_id}"
        assert published["state"] == "done"
        assert published["doi"] == expected_doi
        assert published["conceptdoi"] == expected_concept_doi

        fetched = service.get_deposition(deposition_id)
        assert fetched == published
        assert service.get_doi(deposition_id) == expected_doi


def test_zenodo_service_errors_against_fakenodo(test_app, clean_database, fakenodo_url, tmp_path, monkeypatch):
    monkeypatch.setattr("app.features.zenodo.services.uploads_folder_name", lambda: str(tmp_path))

    with test_app.app_context():
        user, dataset, feature_model = _create_dataset_with_model("contract-errors@example.com", tmp_path)
        service = ZenodoService()

        with pytest.raises(Exception, match="Failed to get deposition"):
            service.get_deposition(999)

        with pytest.raises(Exception, match="Failed to get deposition"):
            service.get_doi(999)

        with pytest.raises(Exception, match="Failed to upload files"):
            service.upload_file(dataset, 999, feature_model, user=user)

        created = service.create_new_deposition(dataset)
        deposition_id = created["id"]

        # Publishing without files is rejected and must not assign a DOI.
        with pytest.raises(Exception, match="Failed to publish deposition"):
            service.publish_deposition(deposition_id)
        assert service.get_doi(deposition_id) is None

        # After uploading and publishing, neither re-publishing nor late uploads succeed.
        service.upload_file(dataset, deposition_id, feature_model, user=user)
        published = service.publish_deposition(deposition_id)

        with pytest.raises(Exception, match="Failed to publish deposition"):
            service.publish_deposition(deposition_id)

        with pytest.raises(Exception, match="Failed to upload files"):
            service.upload_file(dataset, deposition_id, feature_model, user=user)

        assert service.get_deposition(deposition_id) == published
