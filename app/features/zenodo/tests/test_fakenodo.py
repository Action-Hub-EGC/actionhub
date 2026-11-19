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
