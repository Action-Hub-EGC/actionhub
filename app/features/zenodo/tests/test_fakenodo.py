import hashlib
import io

import pytest

from fakenodo.app import create_app
from fakenodo.store import DepositionStore

pytestmark = pytest.mark.integration

DEPOSITIONS_URL = "/api/deposit/depositions"


@pytest.fixture
def fakenodo_client(tmp_path):
    app = create_app(DepositionStore(tmp_path / "fakenodo.sqlite3"))
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health_endpoint(fakenodo_client):
    response = fakenodo_client.get("/health")

    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_create_deposition(fakenodo_client):
    response = fakenodo_client.post(
        DEPOSITIONS_URL,
        json={"metadata": {"title": "A dataset", "upload_type": "dataset"}},
    )

    assert response.status_code == 201
    deposition = response.get_json()
    assert deposition["id"] == 1
    assert deposition["conceptrecid"] == 1
    assert deposition["doi"] is None
    assert deposition["state"] == "unsubmitted"
    assert deposition["metadata"] == {"title": "A dataset", "upload_type": "dataset"}
    assert deposition["files"] == []
    assert deposition["version"] == 1


def test_create_deposition_accepts_empty_body(fakenodo_client):
    response = fakenodo_client.post(DEPOSITIONS_URL)

    assert response.status_code == 201
    assert response.get_json()["metadata"] == {}


def test_create_deposition_rejects_non_object_json(fakenodo_client):
    response = fakenodo_client.post(DEPOSITIONS_URL, json=["not", "an", "object"])

    assert response.status_code == 400
    assert response.get_json() == {"message": "The request body must be a JSON object"}


def test_create_deposition_rejects_invalid_metadata(fakenodo_client):
    response = fakenodo_client.post(DEPOSITIONS_URL, json={"metadata": "invalid"})

    assert response.status_code == 400
    assert response.get_json() == {"message": "metadata must be a JSON object"}


def test_create_deposition_rejects_malformed_json(fakenodo_client):
    response = fakenodo_client.post(
        DEPOSITIONS_URL,
        data="{bad",
        content_type="application/json",
    )

    assert response.status_code == 400
    assert response.get_json() == {"message": "Malformed JSON"}


def test_create_deposition_rejects_wrong_content_type(fakenodo_client):
    response = fakenodo_client.post(
        DEPOSITIONS_URL,
        data="metadata",
        content_type="text/plain",
    )

    assert response.status_code == 415
    assert response.get_json() == {"message": "Content-Type must be application/json"}


def test_list_depositions(fakenodo_client):
    fakenodo_client.post(DEPOSITIONS_URL, json={"metadata": {"title": "First"}})
    fakenodo_client.post(DEPOSITIONS_URL, json={"metadata": {"title": "Second"}})

    response = fakenodo_client.get(DEPOSITIONS_URL)

    assert response.status_code == 200
    depositions = response.get_json()
    assert [deposition["id"] for deposition in depositions] == [1, 2]
    assert depositions[0]["metadata"] == {"title": "First"}
    assert depositions[1]["metadata"] == {"title": "Second"}


def test_get_deposition(fakenodo_client):
    created = fakenodo_client.post(
        DEPOSITIONS_URL,
        json={"metadata": {"title": "Dataset"}},
    ).get_json()

    response = fakenodo_client.get(f"{DEPOSITIONS_URL}/{created['id']}")

    assert response.status_code == 200
    assert response.get_json() == created


def test_upload_file_stores_name_size_and_checksum_and_lists_it(fakenodo_client):
    created = fakenodo_client.post(
        DEPOSITIONS_URL,
        json={"metadata": {"title": "Dataset"}},
    ).get_json()
    content = b"feature data"

    upload = fakenodo_client.post(
        f"{DEPOSITIONS_URL}/{created['id']}/files",
        data={"name": "dataset.uvl", "file": (io.BytesIO(content), "ignored-name.uvl")},
        content_type="multipart/form-data",
    )

    assert upload.status_code == 201
    assert upload.get_json() == {
        "id": 1,
        "filename": "dataset.uvl",
        "filesize": len(content),
        "checksum": f"md5:{hashlib.md5(content).hexdigest()}",
    }

    deposition = fakenodo_client.get(f"{DEPOSITIONS_URL}/{created['id']}").get_json()
    assert deposition["files"] == [upload.get_json()]


def test_upload_file_is_rejected_after_publishing(fakenodo_client):
    created = fakenodo_client.post(
        DEPOSITIONS_URL,
        json={"metadata": {"title": "Dataset"}},
    ).get_json()
    upload = fakenodo_client.post(
        f"{DEPOSITIONS_URL}/{created['id']}/files",
        data={"name": "before-publish.uvl", "file": (io.BytesIO(b"published"), "ignored.uvl")},
        content_type="multipart/form-data",
    )
    assert upload.status_code == 201

    store = fakenodo_client.application.extensions.get("fakenodo_store")
    assert store is not None
    store.update(created["id"], state="done")

    response = fakenodo_client.post(
        f"{DEPOSITIONS_URL}/{created['id']}/files",
        data={"file": (io.BytesIO(b"late file"), "late.txt")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json() == {"message": "Cannot upload files to a published deposition"}


def test_upload_file_rejects_missing_file(fakenodo_client):
    created = fakenodo_client.post(DEPOSITIONS_URL).get_json()

    response = fakenodo_client.post(
        f"{DEPOSITIONS_URL}/{created['id']}/files",
        data={"name": "missing.uvl"},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json() == {"message": "file is required"}


def test_upload_file_rejects_unknown_deposition(fakenodo_client):
    response = fakenodo_client.post(
        f"{DEPOSITIONS_URL}/999/files",
        data={"file": (io.BytesIO(b"content"), "model.uvl")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 404
    assert response.get_json() == {"message": "Deposition not found"}


def test_upload_file_uses_filename_when_name_is_not_sent(fakenodo_client):
    created = fakenodo_client.post(DEPOSITIONS_URL).get_json()

    response = fakenodo_client.post(
        f"{DEPOSITIONS_URL}/{created['id']}/files",
        data={"file": (io.BytesIO(b"content"), "fallback.uvl")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 201
    assert response.get_json()["filename"] == "fallback.uvl"


def test_get_unknown_deposition_returns_404(fakenodo_client):
    response = fakenodo_client.get(f"{DEPOSITIONS_URL}/999")

    assert response.status_code == 404
    assert response.get_json() == {"message": "Deposition not found"}


def test_delete_deposition(fakenodo_client):
    created = fakenodo_client.post(DEPOSITIONS_URL).get_json()

    response = fakenodo_client.delete(f"{DEPOSITIONS_URL}/{created['id']}")

    assert response.status_code == 204
    assert response.data == b""
    assert fakenodo_client.get(f"{DEPOSITIONS_URL}/{created['id']}").status_code == 404


def test_delete_unknown_deposition_returns_404(fakenodo_client):
    response = fakenodo_client.delete(f"{DEPOSITIONS_URL}/999")

    assert response.status_code == 404
    assert response.get_json() == {"message": "Deposition not found"}


def _create_with_file(client, title="Dataset"):
    created = client.post(DEPOSITIONS_URL, json={"metadata": {"title": title}}).get_json()
    client.post(
        f"{DEPOSITIONS_URL}/{created['id']}/files",
        data={"file": (io.BytesIO(b"content"), "model.uvl")},
        content_type="multipart/form-data",
    )
    return created


def test_publish_assigns_doi_and_concept_doi(fakenodo_client):
    created = _create_with_file(fakenodo_client)

    response = fakenodo_client.post(f"{DEPOSITIONS_URL}/{created['id']}/actions/publish")

    assert response.status_code == 202
    published = response.get_json()
    assert published["state"] == "done"
    assert published["doi"] == f"10.5072/fakenodo.{created['id']}"
    assert published["conceptdoi"] == f"10.5072/fakenodo.concept.{created['conceptrecid']}"
    assert published["doi"] != published["conceptdoi"]


def test_published_doi_appears_in_get(fakenodo_client):
    created = _create_with_file(fakenodo_client)
    published = fakenodo_client.post(f"{DEPOSITIONS_URL}/{created['id']}/actions/publish").get_json()

    deposition = fakenodo_client.get(f"{DEPOSITIONS_URL}/{created['id']}").get_json()

    assert deposition == published
    assert deposition["doi"] == published["doi"]


def test_published_dois_are_unique(fakenodo_client):
    dois = []
    for title in ("First", "Second", "Third"):
        created = _create_with_file(fakenodo_client, title)
        published = fakenodo_client.post(f"{DEPOSITIONS_URL}/{created['id']}/actions/publish").get_json()
        dois.append(published["doi"])

    assert len(set(dois)) == len(dois)


def test_publish_rejects_deposition_without_files(fakenodo_client):
    created = fakenodo_client.post(DEPOSITIONS_URL).get_json()

    response = fakenodo_client.post(f"{DEPOSITIONS_URL}/{created['id']}/actions/publish")

    assert response.status_code == 400
    assert response.get_json() == {"message": "Minimum one file must be provided."}
    deposition = fakenodo_client.get(f"{DEPOSITIONS_URL}/{created['id']}").get_json()
    assert deposition["state"] == "unsubmitted"
    assert deposition["doi"] is None
    assert deposition["conceptdoi"] is None


def test_publish_rejects_already_published_deposition(fakenodo_client):
    created = _create_with_file(fakenodo_client)
    first = fakenodo_client.post(f"{DEPOSITIONS_URL}/{created['id']}/actions/publish").get_json()

    response = fakenodo_client.post(f"{DEPOSITIONS_URL}/{created['id']}/actions/publish")

    assert response.status_code == 400
    assert response.get_json() == {"message": "Deposition is already published"}
    assert fakenodo_client.get(f"{DEPOSITIONS_URL}/{created['id']}").get_json() == first


def test_publish_unknown_deposition_returns_404(fakenodo_client):
    response = fakenodo_client.post(f"{DEPOSITIONS_URL}/999/actions/publish")

    assert response.status_code == 404
    assert response.get_json() == {"message": "Deposition not found"}
