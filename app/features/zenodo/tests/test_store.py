import sqlite3

import pytest

from fakenodo.store import DepositionStore

pytestmark = pytest.mark.unit


def test_create_and_get_persisted_deposition(tmp_path):
    store = DepositionStore(tmp_path / "fakenodo.sqlite3")

    deposition = store.create(
        42,
        metadata={"title": "Stable DOI"},
        files=[{"filename": "model.uvl"}],
    )

    assert deposition == {
        "id": 42,
        "conceptrecid": 42,
        "conceptdoi": None,
        "doi": None,
        "state": "unsubmitted",
        "metadata": {"title": "Stable DOI"},
        "files": [{"filename": "model.uvl"}],
        "version": 1,
    }
    assert store.get(42) == deposition


def test_deposition_survives_store_reinitialization(tmp_path):
    database = tmp_path / "fakenodo.sqlite3"
    store = DepositionStore(database)
    store.create(
        7,
        conceptrecid=7,
        doi="10.5072/fakenodo.7",
        state="done",
        metadata={"title": "Persistent"},
        files=[{"filename": "data.uvl"}],
        version=1,
    )

    restarted_store = DepositionStore(database)

    assert restarted_store.get(7)["doi"] == "10.5072/fakenodo.7"
    assert restarted_store.get(7)["state"] == "done"


def test_update_and_delete_deposition(tmp_path):
    store = DepositionStore(tmp_path / "fakenodo.sqlite3")
    store.create(3)

    updated = store.update(
        3,
        doi="10.5072/fakenodo.3",
        state="done",
        metadata={"title": "Published"},
        files=[{"filename": "data.uvl"}],
        version=2,
    )

    assert updated["doi"] == "10.5072/fakenodo.3"
    assert updated["state"] == "done"
    assert updated["metadata"] == {"title": "Published"}
    assert updated["files"] == [{"filename": "data.uvl"}]
    assert updated["version"] == 2
    assert store.delete(3) is True
    assert store.get(3) is None
    assert store.delete(3) is False


def test_list_and_auto_increment(tmp_path):
    store = DepositionStore(tmp_path / "fakenodo.sqlite3")
    first = store.create(metadata={"title": "First"})
    second = store.create(metadata={"title": "Second"})

    assert first["id"] == 1
    assert second["id"] == 2
    assert [item["id"] for item in store.list()] == [1, 2]


def test_deleted_id_is_not_reused(tmp_path):
    store = DepositionStore(tmp_path / "fakenodo.sqlite3")
    store.create(metadata={"title": "First"})
    second = store.create(metadata={"title": "Second"})
    assert store.delete(second["id"]) is True

    third = store.create(metadata={"title": "Third"})

    assert third["id"] == 3


def test_rejects_invalid_state(tmp_path):
    store = DepositionStore(tmp_path / "fakenodo.sqlite3")

    with pytest.raises(ValueError, match="unsubmitted.*done"):
        store.create(state="draft")


def test_publish_keeps_existing_concept_doi(tmp_path):
    store = DepositionStore(tmp_path / "fakenodo.sqlite3")
    store.create(
        2,
        conceptrecid=1,
        conceptdoi="10.5072/fakenodo.concept.1",
        files=[{"filename": "v2.uvl"}],
        version=2,
    )

    published = store.publish(2)

    assert published["doi"] == "10.5072/fakenodo.2"
    assert published["conceptdoi"] == "10.5072/fakenodo.concept.1"


def test_publish_returns_none_for_unknown_deposition(tmp_path):
    store = DepositionStore(tmp_path / "fakenodo.sqlite3")

    assert store.publish(999) is None


def test_store_adds_conceptdoi_column_to_old_databases(tmp_path):
    database = tmp_path / "fakenodo.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("""
            CREATE TABLE depositions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conceptrecid INTEGER,
                doi TEXT,
                state TEXT NOT NULL CHECK (state IN ('unsubmitted', 'done')),
                metadata TEXT NOT NULL,
                files TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1
            )
            """)
        connection.execute(
            "INSERT INTO depositions (id, conceptrecid, state, metadata, files) VALUES (1, 1, 'unsubmitted', '{}', ?)",
            ('[{"filename": "old.uvl"}]',),
        )
    connection.close()

    store = DepositionStore(database)

    assert store.get(1)["conceptdoi"] is None
    assert store.publish(1)["conceptdoi"] == "10.5072/fakenodo.concept.1"


def test_new_version_returns_none_for_unknown_deposition(tmp_path):
    store = DepositionStore(tmp_path / "fakenodo.sqlite3")

    assert store.new_version(999) is None


def test_list_versions_returns_only_the_concept_in_version_order(tmp_path):
    store = DepositionStore(tmp_path / "fakenodo.sqlite3")
    store.create(1, state="done", files=[{"checksum": "md5:a"}])
    store.create(2, conceptrecid=1, version=2)
    store.create(3)

    assert [deposition["id"] for deposition in store.list_versions(1)] == [1, 2]
