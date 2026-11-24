"""Seeder with known activity values for the dashboard tests (#65)."""

import pytest

from app import db
from app.features.metrics.seeders import ACTIVITY_PLAN, MetricsSeeder
from app.features.metrics.services import MetricsService
from app.features.metrics.tests.test_service import make_dataset, make_user

pytestmark = pytest.mark.service


def test_metrics_seeder_creates_the_known_plan(test_app, clean_database):
    with test_app.app_context():
        owner = make_user("evolution-seed@example.com")
        make_dataset(owner.id, "seeded-one")
        make_dataset(owner.id, "seeded-two")
        db.session.commit()

        MetricsSeeder().run()

        series = MetricsService().owner_activity_by_month(owner.id, months=4)
        expected = []
        for position, _row in enumerate(series):
            _months_ago, view_count, download_count = ACTIVITY_PLAN[3 - position]
            expected.append((download_count * 2, view_count * 2))

        assert [(row["downloads"], row["views"]) for row in series] == expected
        # The third month of the plan has no activity and still appears.
        quiet = series[-3]
        assert (quiet["downloads"], quiet["views"]) == (0, 0)
