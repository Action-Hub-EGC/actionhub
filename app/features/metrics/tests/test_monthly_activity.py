"""Monthly evolution of the owner's activity (#63)."""

from datetime import datetime, timezone

import pytest

from app import db
from app.features.metrics.services import MetricsService
from app.features.metrics.tests.test_service import (
    add_dataset_download,
    add_dataset_view,
    make_dataset,
    make_user,
)

pytestmark = pytest.mark.service

TODAY = datetime(2024, 4, 15, 12, 0, 0, tzinfo=timezone.utc)


def test_monthly_series_fills_quiet_months_with_zero(test_app, clean_database):
    with test_app.app_context():
        owner = make_user("evolution-owner@example.com")
        stranger = make_user("evolution-stranger@example.com")
        mine = make_dataset(owner.id, "mine")
        foreign = make_dataset(stranger.id, "foreign")

        add_dataset_view(mine.id, "jan-a", datetime(2024, 1, 5, 10))
        add_dataset_view(mine.id, "jan-b", datetime(2024, 1, 20, 10))
        add_dataset_download(mine.id, "jan-a", datetime(2024, 1, 6, 10))

        add_dataset_view(mine.id, "mar-a", datetime(2024, 3, 3, 10))
        add_dataset_download(mine.id, "mar-a", datetime(2024, 3, 3, 11))
        add_dataset_download(mine.id, "mar-b", datetime(2024, 3, 4, 11))

        for index in range(3):
            add_dataset_view(mine.id, f"apr-{index}", datetime(2024, 4, index + 1, 10))

        # Other owners and orphan records never enter this series.
        add_dataset_view(foreign.id, "foreign", datetime(2024, 1, 5, 10))
        add_dataset_download(foreign.id, "foreign", datetime(2024, 1, 5, 11))
        add_dataset_view(None, "orphan", datetime(2024, 1, 5, 12))
        add_dataset_download(None, "orphan", datetime(2024, 1, 5, 12))
        db.session.commit()

        series = MetricsService().owner_activity_by_month(owner.id, months=4, today=TODAY)

        assert [row["month"] for row in series] == ["2024-01", "2024-02", "2024-03", "2024-04"]
        assert [row["label"] for row in series] == ["ene 2024", "feb 2024", "mar 2024", "abr 2024"]
        assert [(row["downloads"], row["views"]) for row in series] == [
            (1, 2),
            (0, 0),
            (2, 1),
            (0, 3),
        ]


def test_owner_summary_includes_the_monthly_series(test_app, clean_database):
    with test_app.app_context():
        owner = make_user("evolution-summary@example.com")
        dataset = make_dataset(owner.id, "summary")
        add_dataset_view(dataset.id, "a", datetime(2024, 4, 1, 10))
        add_dataset_view(dataset.id, "b", datetime(2024, 4, 1, 11))
        add_dataset_download(dataset.id, "a", datetime(2024, 4, 1, 12))
        db.session.commit()

        metrics = MetricsService().owner_summary(owner.id, today=TODAY)

        assert metrics["activity_by_month"][-1] == {
            "month": "2024-04",
            "label": "abr 2024",
            "downloads": 1,
            "views": 2,
        }
        assert metrics["activity_max"] == 2


def test_empty_account_has_a_zeroed_series_and_a_safe_divisor(test_app, clean_database):
    with test_app.app_context():
        owner = make_user("evolution-empty@example.com")
        db.session.commit()

        metrics = MetricsService().owner_summary(owner.id, today=TODAY)

        assert len(metrics["activity_by_month"]) == 6
        assert all(row["downloads"] == 0 and row["views"] == 0 for row in metrics["activity_by_month"])
        assert metrics["activity_max"] == 1
