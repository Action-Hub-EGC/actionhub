"""Deterministic activity records for the personal dashboard (#65).

Runs after the dataset seeder and gives every seeded dataset a small,
repeatable history: two active months and one quiet month. Tests can then
assert exact monthly counts instead of depending on wall-clock data.
"""

from datetime import datetime, timezone

from splent_framework.seeders.BaseSeeder import BaseSeeder

from app.features.dataset.models import BaseDataset, DSDownloadRecord, DSViewRecord

# (months ago, views, downloads). Offset 2 is deliberately empty.
ACTIVITY_PLAN = (
    (0, 2, 1),
    (1, 1, 1),
    (2, 0, 0),
    (3, 1, 0),
)


def month_start(now: datetime, months_ago: int) -> datetime:
    index = now.year * 12 + (now.month - 1) - months_ago
    year, month_index = divmod(index, 12)
    return datetime(year, month_index + 1, 15, 12, 0, 0)


class MetricsSeeder(BaseSeeder):
    priority = 3

    def run(self):
        datasets = BaseDataset.query.order_by(BaseDataset.id).all()
        if not datasets:
            return

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        views = []
        downloads = []
        for dataset in datasets:
            for months_ago, view_count, download_count in ACTIVITY_PLAN:
                when = month_start(now, months_ago)
                for index in range(view_count):
                    views.append(
                        DSViewRecord(
                            dataset_id=dataset.id,
                            view_date=when,
                            view_cookie=f"seed-view-{dataset.id}-{months_ago}-{index}",
                        )
                    )
                for index in range(download_count):
                    downloads.append(
                        DSDownloadRecord(
                            dataset_id=dataset.id,
                            download_date=when,
                            download_cookie=f"seed-download-{dataset.id}-{months_ago}-{index}",
                        )
                    )

        self.seed(views)
        self.seed(downloads)
