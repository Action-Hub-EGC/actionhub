"""Repository-level tests for dataset — queries against a real database."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app.features.auth.repositories import UserRepository
from app.features.dataset import repositories as dataset_repositories
from app.features.dataset.models import PublicationType
from app.features.dataset.repositories import (
    DataSetRepository,
    DOIMappingRepository,
    DSDownloadRecordRepository,
    DSMetaDataRepository,
    DSViewRecordRepository,
)

pytestmark = pytest.mark.repository


def _make_user(email):
    return UserRepository().create(email=email, password="secret")


def _make_dataset(user, title="Sample dataset", doi=None, created_at=None):
    meta = DSMetaDataRepository().create(
        title=title,
        description=f"Description for {title}",
        publication_type=PublicationType.DATA_MANAGEMENT_PLAN,
        dataset_doi=doi,
        tags="tag1,tag2",
    )
    return DataSetRepository().create(
        user_id=user.id,
        ds_meta_data_id=meta.id,
        created_at=created_at or datetime.now(timezone.utc),
    )


def test_get_synchronized_and_unsynchronized_split_on_dataset_doi(test_app, clean_database):
    with test_app.app_context():
        owner = _make_user("owner@example.com")
        other = _make_user("other@example.com")
        synced = _make_dataset(owner, title="Synced", doi="10.1234/synced")
        unsynced = _make_dataset(owner, title="Local")
        _make_dataset(other, title="Someone else", doi="10.1234/other")

        repo = DataSetRepository()
        assert [d.id for d in repo.get_synchronized(owner.id)] == [synced.id]
        assert [d.id for d in repo.get_unsynchronized(owner.id)] == [unsynced.id]


def test_get_unsynchronized_dataset_is_scoped_to_owner_and_missing_doi(test_app, clean_database):
    with test_app.app_context():
        owner = _make_user("owner@example.com")
        intruder = _make_user("intruder@example.com")
        local = _make_dataset(owner, title="Local")
        synced = _make_dataset(owner, title="Synced", doi="10.1234/synced")

        repo = DataSetRepository()
        assert repo.get_unsynchronized_dataset(owner.id, local.id).id == local.id
        # A published dataset is no longer "unsynchronized"...
        assert repo.get_unsynchronized_dataset(owner.id, synced.id) is None
        # ...and another user must not reach it either.
        assert repo.get_unsynchronized_dataset(intruder.id, local.id) is None


def test_counts_split_datasets_across_every_user(test_app, clean_database):
    with test_app.app_context():
        owner = _make_user("owner@example.com")
        other = _make_user("other@example.com")
        _make_dataset(owner, title="A", doi="10.1234/a")
        _make_dataset(other, title="B", doi="10.1234/b")
        _make_dataset(owner, title="C")

        repo = DataSetRepository()
        assert repo.count_synchronized_datasets() == 2
        assert repo.count_unsynchronized_datasets() == 1
        assert repo.count_for_user(owner.id) == 2
        assert repo.count_for_user(other.id) == 1


def test_paginate_for_user_returns_newest_first_and_respects_page_size(test_app, clean_database):
    with test_app.app_context():
        owner = _make_user("owner@example.com")
        other = _make_user("other@example.com")
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        oldest = _make_dataset(owner, title="Oldest", created_at=base)
        middle = _make_dataset(owner, title="Middle", created_at=base + timedelta(days=1))
        newest = _make_dataset(owner, title="Newest", created_at=base + timedelta(days=2))
        _make_dataset(other, title="Not mine", created_at=base + timedelta(days=3))

        page = DataSetRepository().paginate_for_user(owner.id, page=1, per_page=2)
        assert page.total == 3
        assert [d.id for d in page.items] == [newest.id, middle.id]

        second = DataSetRepository().paginate_for_user(owner.id, page=2, per_page=2)
        assert [d.id for d in second.items] == [oldest.id]


def test_latest_synchronized_caps_the_result_at_five_newest(test_app, clean_database):
    with test_app.app_context():
        owner = _make_user("owner@example.com")
        synced_ids = [_make_dataset(owner, title=f"Synced {i}", doi=f"10.1234/s{i}").id for i in range(7)]
        _make_dataset(owner, title="Local")

        latest = DataSetRepository().latest_synchronized()
        assert [d.id for d in latest] == sorted(synced_ids, reverse=True)[:5]


def test_filter_by_doi_finds_metadata_or_returns_none(test_app, clean_database):
    with test_app.app_context():
        owner = _make_user("owner@example.com")
        dataset = _make_dataset(owner, title="Published", doi="10.1234/published")

        repo = DSMetaDataRepository()
        found = repo.filter_by_doi("10.1234/published")
        assert found is not None
        assert found.id == dataset.ds_meta_data_id
        assert found.title == "Published"
        assert repo.filter_by_doi("10.1234/nope") is None


def test_doi_mapping_resolves_old_doi_to_the_new_row(test_app, clean_database):
    with test_app.app_context():
        repo = DOIMappingRepository()
        repo.create(dataset_doi_old="10.1234/old", dataset_doi_new="10.5678/new")

        mapping = repo.get_new_doi("10.1234/old")
        assert mapping is not None
        assert mapping.dataset_doi_new == "10.5678/new"
        assert repo.get_new_doi("10.5678/new") is None


def test_download_records_are_looked_up_by_user_dataset_and_cookie(test_app, clean_database):
    with test_app.app_context():
        owner = _make_user("owner@example.com")
        dataset = _make_dataset(owner, title="Downloadable")

        repo = DSDownloadRecordRepository()
        assert repo.total_dataset_downloads() == 0

        record = repo.create(
            user_id=owner.id,
            dataset_id=dataset.id,
            download_date=datetime.now(timezone.utc),
            download_cookie="cookie-a",
        )

        assert repo.find_by_user_dataset_cookie(owner.id, dataset.id, "cookie-a") is not None
        assert repo.find_by_user_dataset_cookie(owner.id, dataset.id, "cookie-b") is None
        assert repo.find_by_user_dataset_cookie(None, dataset.id, "cookie-a") is None
        assert repo.total_dataset_downloads() == 1

        repo.create(
            user_id=owner.id,
            dataset_id=dataset.id,
            download_date=datetime.now(timezone.utc),
            download_cookie="cookie-b",
        )
        assert repo.total_dataset_downloads() == 2

        # Deleting a row lowers the count even though the highest id survives.
        repo.delete(record.id)
        assert repo.total_dataset_downloads() == 1


def test_total_dataset_views_tracks_created_records(test_app, clean_database):
    with test_app.app_context():
        owner = _make_user("owner@example.com")
        dataset = _make_dataset(owner, title="Viewable")

        repo = DSViewRecordRepository()
        assert repo.total_dataset_views() == 0

        records = [
            repo.create(
                user_id=owner.id,
                dataset_id=dataset.id,
                view_date=datetime.now(timezone.utc),
                view_cookie=cookie,
            )
            for cookie in ("cookie-a", "cookie-b")
        ]

        assert repo.total_dataset_views() == 2

        # Deleting a row lowers the count even though the highest id survives.
        repo.delete(records[0].id)
        assert repo.total_dataset_views() == 1


# --- One record per (user or anonymous, dataset, cookie) in the database (#67) ---


def _download(repo, user_id, dataset_id, cookie):
    return repo.create(
        user_id=user_id,
        dataset_id=dataset_id,
        download_date=datetime.now(timezone.utc),
        download_cookie=cookie,
    )


@pytest.mark.parametrize("anonymous", [False, True])
def test_the_database_rejects_a_duplicate_download_record(test_app, clean_database, anonymous):
    with test_app.app_context():
        owner = _make_user("owner@example.com")
        dataset = _make_dataset(owner, title="Downloadable")
        user_id = None if anonymous else owner.id
        repo = DSDownloadRecordRepository()
        _download(repo, user_id, dataset.id, "cookie-a")

        with pytest.raises(IntegrityError):
            _download(repo, user_id, dataset.id, "cookie-a")
        repo.session.rollback()

        assert repo.total_dataset_downloads() == 1


def test_the_database_rejects_a_duplicate_anonymous_view_record(test_app, clean_database):
    with test_app.app_context():
        owner = _make_user("owner@example.com")
        dataset = _make_dataset(owner, title="Viewable")
        repo = DSViewRecordRepository()
        values = {"user_id": None, "dataset_id": dataset.id, "view_cookie": "cookie-a"}
        repo.create(view_date=datetime.now(timezone.utc), **values)

        with pytest.raises(IntegrityError):
            repo.create(view_date=datetime.now(timezone.utc), **values)
        repo.session.rollback()

        assert repo.total_dataset_views() == 1


def test_user_key_is_zero_for_anonymous_records_and_the_user_id_otherwise(test_app, clean_database):
    with test_app.app_context():
        owner = _make_user("owner@example.com")
        dataset = _make_dataset(owner, title="Downloadable")
        repo = DSDownloadRecordRepository()
        anonymous = _download(repo, None, dataset.id, "cookie-a")
        logged_in = _download(repo, owner.id, dataset.id, "cookie-a")

        repo.session.refresh(anonymous)
        repo.session.refresh(logged_in)
        assert anonymous.user_key == 0
        assert logged_in.user_key == owner.id


def test_record_once_counts_each_user_dataset_and_cookie_once(test_app, clean_database):
    with test_app.app_context():
        owner = _make_user("owner@example.com")
        dataset = _make_dataset(owner, title="Downloadable")
        repo = DSDownloadRecordRepository()

        assert repo.record_once(None, dataset.id, "cookie-a") is True
        assert repo.record_once(None, dataset.id, "cookie-a") is False
        assert repo.record_once(owner.id, dataset.id, "cookie-a") is True
        assert repo.record_once(owner.id, dataset.id, "cookie-a") is False
        assert repo.total_dataset_downloads() == 2


@pytest.mark.parametrize(
    "repository_class, cookie_field",
    [
        (DSDownloadRecordRepository, "download_cookie"),
        (DSViewRecordRepository, "view_cookie"),
    ],
)
def test_record_once_survives_a_concurrent_insert_of_the_same_record(
    test_app, clean_database, monkeypatch, repository_class, cookie_field
):
    """Two requests both miss the lookup; the second insert must not fail or count."""
    with test_app.app_context():
        owner = _make_user("owner@example.com")
        dataset = _make_dataset(owner, title="Raced")
        repo = repository_class()
        assert repo.record_once(None, dataset.id, "cookie-a") is True

        real_find = dataset_repositories._find
        calls = []

        def racing_find(repository, key):
            # The first lookup misses, as in the request that loses the race.
            calls.append(key)
            return None if len(calls) == 1 else real_find(repository, key)

        monkeypatch.setattr(dataset_repositories, "_find", racing_find)

        assert repo.record_once(None, dataset.id, "cookie-a") is False
        assert len(calls) == 2  # Missed lookup, failed insert, lookup that finds it.
        assert repo.count() == 1
        assert repo.model.query.filter_by(**{cookie_field: "cookie-a"}).count() == 1


def test_record_once_does_not_hide_other_integrity_errors(test_app, clean_database):
    with test_app.app_context():
        repo = DSDownloadRecordRepository()

        # No dataset 999: the foreign key fails, and that is not a duplicate.
        with pytest.raises(IntegrityError):
            repo.record_once(None, 999, "cookie-a")


def test_global_totals_ignore_records_without_a_dataset(test_app, clean_database):
    """The home page totals must add up to the per-dataset counts (#67)."""
    with test_app.app_context():
        owner = _make_user("owner@example.com")
        dataset = _make_dataset(owner, title="Counted")
        downloads, views = DSDownloadRecordRepository(), DSViewRecordRepository()
        now = datetime.now(timezone.utc)
        for dataset_id in (dataset.id, None):
            downloads.create(dataset_id=dataset_id, download_date=now, download_cookie="cookie-a")
            views.create(dataset_id=dataset_id, view_date=now, view_cookie="cookie-a")

        assert downloads.total_dataset_downloads() == 1
        assert views.total_dataset_views() == 1
