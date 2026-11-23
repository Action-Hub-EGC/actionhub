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


def _upload(client, deposition_id, content, name="model.uvl"):
    return client.post(
        f"{DEPOSITIONS_URL}/{deposition_id}/files",
        data={"file": (io.BytesIO(content), name)},
        content_type="multipart/form-data",
    )


def _published(client, title="Dataset", content=b"v1"):
    created = client.post(DEPOSITIONS_URL, json={"metadata": {"title": title}}).get_json()
    _upload(client, created["id"], content)
    return client.post(f"{DEPOSITIONS_URL}/{created['id']}/actions/publish").get_json()


def _new_version_draft(client, deposition_id):
    response = client.post(f"{DEPOSITIONS_URL}/{deposition_id}/actions/newversion")
    assert response.status_code == 201
    return client.get(response.get_json()["links"]["latest_draft"]).get_json()


def test_metadata_change_keeps_the_same_doi(fakenodo_client):
    published = _published(fakenodo_client)

    response = fakenodo_client.put(
        f"{DEPOSITIONS_URL}/{published['id']}",
        json={"metadata": {"title": "Better title"}},
    )

    assert response.status_code == 200
    updated = response.get_json()
    assert updated["metadata"] == {"title": "Better title"}
    assert updated["doi"] == published["doi"]
    assert updated["conceptdoi"] == published["conceptdoi"]
    assert updated["state"] == "done"
    assert fakenodo_client.get(f"{DEPOSITIONS_URL}/{published['id']}").get_json() == updated


def test_new_version_creates_a_linked_draft_with_copied_files_and_metadata(fakenodo_client):
    published = _published(fakenodo_client, title="Workflow")

    response = fakenodo_client.post(f"{DEPOSITIONS_URL}/{published['id']}/actions/newversion")

    assert response.status_code == 201
    body = response.get_json()
    assert body["id"] == published["id"]
    assert body["doi"] == published["doi"]

    draft = fakenodo_client.get(body["links"]["latest_draft"]).get_json()
    assert draft["id"] != published["id"]
    assert draft["state"] == "unsubmitted"
    assert draft["doi"] is None
    assert draft["conceptrecid"] == published["conceptrecid"]
    assert draft["conceptdoi"] == published["conceptdoi"]
    assert draft["version"] == 2
    assert draft["metadata"] == published["metadata"]
    assert draft["files"] == published["files"]


def test_files_change_and_publish_gives_a_new_doi_and_keeps_the_concept_doi(fakenodo_client):
    v1 = _published(fakenodo_client, content=b"v1")
    draft = _new_version_draft(fakenodo_client, v1["id"])

    old_file = draft["files"][0]["id"]
    assert fakenodo_client.delete(f"{DEPOSITIONS_URL}/{draft['id']}/files/{old_file}").status_code == 204
    assert _upload(fakenodo_client, draft["id"], b"v2").status_code == 201
    response = fakenodo_client.post(f"{DEPOSITIONS_URL}/{draft['id']}/actions/publish")

    assert response.status_code == 202
    v2 = response.get_json()
    assert v2["doi"] == f"10.5072/fakenodo.{draft['id']}"
    assert v2["doi"] != v1["doi"]
    assert v2["conceptdoi"] == v1["conceptdoi"]
    assert fakenodo_client.get(f"{DEPOSITIONS_URL}/{v1['id']}").get_json()["doi"] == v1["doi"]


def test_every_version_shares_the_concept_doi(fakenodo_client):
    versions = [_published(fakenodo_client, content=b"v1")]
    for content in (b"v2", b"v3"):
        draft = _new_version_draft(fakenodo_client, versions[-1]["id"])
        _upload(fakenodo_client, draft["id"], content, name=f"{content.decode()}.uvl")
        versions.append(fakenodo_client.post(f"{DEPOSITIONS_URL}/{draft['id']}/actions/publish").get_json())

    assert [version["version"] for version in versions] == [1, 2, 3]
    assert len({version["doi"] for version in versions}) == 3
    assert {version["conceptdoi"] for version in versions} == {versions[0]["conceptdoi"]}
    assert {version["conceptrecid"] for version in versions} == {versions[0]["conceptrecid"]}


def test_new_version_with_unchanged_files_cannot_be_published(fakenodo_client):
    v1 = _published(fakenodo_client)
    draft = _new_version_draft(fakenodo_client, v1["id"])

    response = fakenodo_client.post(f"{DEPOSITIONS_URL}/{draft['id']}/actions/publish")

    assert response.status_code == 400
    assert response.get_json() == {"message": "New version's files must differ from all previous versions."}
    assert fakenodo_client.get(f"{DEPOSITIONS_URL}/{draft['id']}").get_json()["doi"] is None


def test_new_version_returns_the_existing_draft_instead_of_a_second_one(fakenodo_client):
    v1 = _published(fakenodo_client)

    first = fakenodo_client.post(f"{DEPOSITIONS_URL}/{v1['id']}/actions/newversion").get_json()
    second = fakenodo_client.post(f"{DEPOSITIONS_URL}/{v1['id']}/actions/newversion").get_json()

    assert first["links"]["latest_draft"] == second["links"]["latest_draft"]
    assert len(fakenodo_client.get(DEPOSITIONS_URL).get_json()) == 2


def test_new_version_from_an_old_version_starts_from_the_latest_one(fakenodo_client):
    v1 = _published(fakenodo_client, title="v1 title", content=b"v1")
    draft = _new_version_draft(fakenodo_client, v1["id"])
    fakenodo_client.put(f"{DEPOSITIONS_URL}/{draft['id']}", json={"metadata": {"title": "v2 title"}})
    _upload(fakenodo_client, draft["id"], b"v2", name="v2.uvl")
    v2 = fakenodo_client.post(f"{DEPOSITIONS_URL}/{draft['id']}/actions/publish").get_json()

    v3_draft = _new_version_draft(fakenodo_client, v1["id"])

    assert v3_draft["version"] == 3
    assert v3_draft["metadata"] == v2["metadata"]
    assert v3_draft["files"] == v2["files"]


def test_new_version_rejects_unpublished_deposition(fakenodo_client):
    created = fakenodo_client.post(DEPOSITIONS_URL).get_json()

    response = fakenodo_client.post(f"{DEPOSITIONS_URL}/{created['id']}/actions/newversion")

    assert response.status_code == 400
    assert response.get_json() == {"message": "Only published depositions can have a new version"}


def test_new_version_of_unknown_deposition_returns_404(fakenodo_client):
    response = fakenodo_client.post(f"{DEPOSITIONS_URL}/999/actions/newversion")

    assert response.status_code == 404
    assert response.get_json() == {"message": "Deposition not found"}


def test_update_rejects_missing_metadata(fakenodo_client):
    created = fakenodo_client.post(DEPOSITIONS_URL).get_json()

    response = fakenodo_client.put(f"{DEPOSITIONS_URL}/{created['id']}", json={"title": "no metadata"})

    assert response.status_code == 400
    assert response.get_json() == {"message": "metadata must be a JSON object"}


def test_update_unknown_deposition_returns_404(fakenodo_client):
    response = fakenodo_client.put(f"{DEPOSITIONS_URL}/999", json={"metadata": {}})

    assert response.status_code == 404
    assert response.get_json() == {"message": "Deposition not found"}


def test_delete_file_does_not_reuse_file_ids(fakenodo_client):
    created = fakenodo_client.post(DEPOSITIONS_URL).get_json()
    _upload(fakenodo_client, created["id"], b"a", name="a.uvl")
    _upload(fakenodo_client, created["id"], b"b", name="b.uvl")

    assert fakenodo_client.delete(f"{DEPOSITIONS_URL}/{created['id']}/files/1").status_code == 204
    third = _upload(fakenodo_client, created["id"], b"c", name="c.uvl").get_json()

    files = fakenodo_client.get(f"{DEPOSITIONS_URL}/{created['id']}").get_json()["files"]
    assert [file["filename"] for file in files] == ["b.uvl", "c.uvl"]
    assert third["id"] == 3


def test_delete_file_rejects_published_deposition_and_unknown_file(fakenodo_client):
    published = _published(fakenodo_client)
    draft = fakenodo_client.post(DEPOSITIONS_URL).get_json()

    on_published = fakenodo_client.delete(f"{DEPOSITIONS_URL}/{published['id']}/files/1")
    unknown = fakenodo_client.delete(f"{DEPOSITIONS_URL}/{draft['id']}/files/9")

    assert on_published.status_code == 400
    assert on_published.get_json() == {"message": "Cannot delete files from a published deposition"}
    assert unknown.status_code == 404
    assert unknown.get_json() == {"message": "File not found"}


def test_list_depositions_is_empty_initially_and_excludes_deleted_items(fakenodo_client):
    empty_response = fakenodo_client.get(DEPOSITIONS_URL)
    assert empty_response.status_code == 200
    assert empty_response.get_json() == []

    first = fakenodo_client.post(DEPOSITIONS_URL, json={"metadata": {"title": "First"}}).get_json()
    second = fakenodo_client.post(DEPOSITIONS_URL, json={"metadata": {"title": "Second"}}).get_json()
    third = fakenodo_client.post(DEPOSITIONS_URL, json={"metadata": {"title": "Third"}}).get_json()

    assert fakenodo_client.delete(f"{DEPOSITIONS_URL}/{second['id']}").status_code == 204
    assert fakenodo_client.delete(f"{DEPOSITIONS_URL}/{second['id']}").status_code == 404

    remaining = fakenodo_client.get(DEPOSITIONS_URL)
    assert remaining.status_code == 200
    assert [item["id"] for item in remaining.get_json()] == [first["id"], third["id"]]


def test_delete_published_deposition_removes_it_without_affecting_other_versions(fakenodo_client):
    v1 = _published(fakenodo_client, content=b"v1")
    draft = _new_version_draft(fakenodo_client, v1["id"])
    _upload(fakenodo_client, draft["id"], b"v2", name="v2.uvl")
    v2 = fakenodo_client.post(f"{DEPOSITIONS_URL}/{draft['id']}/actions/publish").get_json()

    deleted = fakenodo_client.delete(f"{DEPOSITIONS_URL}/{v1['id']}")
    assert deleted.status_code == 204
    assert deleted.data == b""
    assert fakenodo_client.get(f"{DEPOSITIONS_URL}/{v1['id']}").status_code == 404

    v2_after = fakenodo_client.get(f"{DEPOSITIONS_URL}/{v2['id']}").get_json()
    assert v2_after["doi"] == v2["doi"]
    assert v2_after["conceptdoi"] == v1["conceptdoi"]

    v3_draft = _new_version_draft(fakenodo_client, v2["id"])
    assert v3_draft["version"] == 3
    assert v3_draft["conceptdoi"] == v1["conceptdoi"]


def test_unknown_route_and_non_integer_id_return_json_404(fakenodo_client):
    for path in ("/api/deposit/unknown", f"{DEPOSITIONS_URL}/not-an-id"):
        response = fakenodo_client.get(path)
        assert response.status_code == 404
        assert response.is_json
        assert response.get_json() == {"message": "Not found"}


def test_upload_file_rejects_empty_filename_without_persisting(fakenodo_client):
    created = fakenodo_client.post(DEPOSITIONS_URL).get_json()

    response = fakenodo_client.post(
        f"{DEPOSITIONS_URL}/{created['id']}/files",
        data={"file": (io.BytesIO(b"data"), "")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json() == {"message": "file name is required"}
    assert fakenodo_client.get(f"{DEPOSITIONS_URL}/{created['id']}").get_json()["files"] == []


def test_delete_file_of_unknown_deposition_returns_404(fakenodo_client):
    response = fakenodo_client.delete(f"{DEPOSITIONS_URL}/999/files/1")

    assert response.status_code == 404
    assert response.get_json() == {"message": "Deposition not found"}


def test_update_metadata_rejects_invalid_requests_without_modifying_deposition(fakenodo_client):
    published = _published(fakenodo_client, title="Original")

    malformed = fakenodo_client.put(
        f"{DEPOSITIONS_URL}/{published['id']}",
        data="{bad",
        content_type="application/json",
    )
    wrong_type = fakenodo_client.put(
        f"{DEPOSITIONS_URL}/{published['id']}",
        data="metadata",
        content_type="text/plain",
    )
    non_object = fakenodo_client.put(
        f"{DEPOSITIONS_URL}/{published['id']}",
        json=["not", "an", "object"],
    )

    assert malformed.status_code == 400
    assert malformed.get_json() == {"message": "Malformed JSON"}
    assert wrong_type.status_code == 415
    assert wrong_type.get_json() == {"message": "Content-Type must be application/json"}
    assert non_object.status_code == 400
    assert non_object.get_json() == {"message": "The request body must be a JSON object"}
    assert fakenodo_client.get(f"{DEPOSITIONS_URL}/{published['id']}").get_json() == published


def test_update_metadata_on_draft_keeps_it_unsubmitted_without_doi(fakenodo_client):
    created = fakenodo_client.post(DEPOSITIONS_URL, json={"metadata": {"title": "Draft"}}).get_json()

    response = fakenodo_client.put(
        f"{DEPOSITIONS_URL}/{created['id']}",
        json={"metadata": {"title": "Updated draft"}},
    )

    assert response.status_code == 200
    updated = response.get_json()
    assert updated["state"] == "unsubmitted"
    assert updated["doi"] is None
    assert updated["metadata"] == {"title": "Updated draft"}


def test_new_version_matching_an_older_published_version_files_is_rejected(fakenodo_client):
    v1 = _published(fakenodo_client, content=b"v1")
    draft_v2 = _new_version_draft(fakenodo_client, v1["id"])
    _upload(fakenodo_client, draft_v2["id"], b"v2", name="v2.uvl")
    v2 = fakenodo_client.post(f"{DEPOSITIONS_URL}/{draft_v2['id']}/actions/publish").get_json()

    # Build v3 by removing v2.uvl so its files match v1 again.
    draft_v3 = _new_version_draft(fakenodo_client, v2["id"])
    v2_file = next(file for file in draft_v3["files"] if file["filename"] == "v2.uvl")
    assert fakenodo_client.delete(f"{DEPOSITIONS_URL}/{draft_v3['id']}/files/{v2_file['id']}").status_code == 204

    response = fakenodo_client.post(f"{DEPOSITIONS_URL}/{draft_v3['id']}/actions/publish")

    assert response.status_code == 400
    assert response.get_json() == {"message": "New version's files must differ from all previous versions."}
    assert fakenodo_client.get(f"{DEPOSITIONS_URL}/{draft_v3['id']}").get_json()["doi"] is None


def test_new_version_with_all_files_deleted_cannot_be_published(fakenodo_client):
    v1 = _published(fakenodo_client, content=b"v1")
    draft = _new_version_draft(fakenodo_client, v1["id"])

    for file in draft["files"]:
        assert fakenodo_client.delete(f"{DEPOSITIONS_URL}/{draft['id']}/files/{file['id']}").status_code == 204

    response = fakenodo_client.post(f"{DEPOSITIONS_URL}/{draft['id']}/actions/publish")

    assert response.status_code == 400
    assert response.get_json() == {"message": "Minimum one file must be provided."}
    assert fakenodo_client.get(f"{DEPOSITIONS_URL}/{draft['id']}").get_json()["doi"] is None
