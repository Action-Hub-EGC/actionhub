"""Per-dataset counts against the database (#67).

The service tests use a fake repository; these check the real queries and that
the profile metrics and the counter service give the same numbers.
"""

from datetime import datetime

import pytest

from app import db
from app.features.dataset.models import DSDownloadRecord, DSViewRecord
from app.features.metrics.repositories import DatasetCounterRepository
from app.features.metrics.services import DatasetCounterService, MetricsService
from app.features.metrics.tests.test_service import make_dataset, make_user

pytestmark = pytest.mark.repository

WHEN = datetime(2024, 5, 1, 12)


def add_view(dataset_id, cookie, user_id=None):
    db.session.add(DSViewRecord(dataset_id=dataset_id, view_cookie=cookie, view_date=WHEN, user_id=user_id))


def add_download(dataset_id, cookie, user_id=None):
    db.session.add(DSDownloadRecord(dataset_id=dataset_id, download_cookie=cookie, download_date=WHEN, user_id=user_id))


def test_counts_group_the_records_by_dataset(test_app, clean_database):
    with test_app.app_context():
        owner = make_user("counter-owner@example.com")
        busy = make_dataset(owner.id, "busy")
        quiet = make_dataset(owner.id, "quiet")
        idle = make_dataset(owner.id, "idle")

        add_view(busy.id, "cookie-a")
        add_view(busy.id, "cookie-a", user_id=owner.id)  # Same browser, now logged in: counts again (#66).
        add_view(busy.id, "cookie-b")
        add_download(busy.id, "cookie-a")
        add_download(busy.id, "cookie-b")
        add_view(quiet.id, "cookie-a")
        add_view(None, "cookie-orphan")  # No dataset: never counted.
        add_download(None, "cookie-orphan")
        db.session.commit()

        counts = DatasetCounterRepository().counts([busy.id, quiet.id, idle.id])

        assert counts == {
            busy.id: {"downloads": 2, "views": 3},
            quiet.id: {"views": 1},
        }


def test_counts_only_returns_the_requested_datasets(test_app, clean_database):
    with test_app.app_context():
        owner = make_user("counter-owner@example.com")
        mine = make_dataset(owner.id, "mine")
        other = make_dataset(owner.id, "other")
        add_download(mine.id, "cookie-a")
        add_download(other.id, "cookie-a")
        db.session.commit()

        assert DatasetCounterRepository().counts([mine.id]) == {mine.id: {"downloads": 1}}
        assert DatasetCounterRepository().counts([]) == {}


def test_profile_metrics_and_counter_service_agree(test_app, clean_database):
    with test_app.app_context():
        owner = make_user("counter-owner@example.com")
        first = make_dataset(owner.id, "first")
        second = make_dataset(owner.id, "second")
        for cookie in ("a", "b", "c"):
            add_view(first.id, cookie)
        add_download(first.id, "a")
        add_view(second.id, "a")
        add_download(second.id, "a")
        add_download(second.id, "b")
        db.session.commit()

        rows = MetricsService().workflows_for_owner(owner.id)
        counts = DatasetCounterService().counts_for_many(row["id"] for row in rows)

        for row in rows:
            assert counts[row["id"]] == {"downloads": row["workflow_downloads"], "views": row["workflow_views"]}
