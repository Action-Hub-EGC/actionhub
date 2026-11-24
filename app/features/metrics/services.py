from datetime import datetime, timezone
from typing import Iterable

from app.features.metrics.repositories import DatasetCounterRepository, MetricsRepository
from app.features.metrics.utils import as_utc

# Short month names for the dashboard chart, in Spanish.
MONTH_LABELS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


class DatasetCounterService:
    """Single source of the download and view counts of a dataset (#67).

    The dataset page, explore, the API and the badge read their numbers from
    here, so they all show the same value. Downloads are unique per user or
    anonymous visitor, browser and dataset (decision #66); views follow the
    same rule. Neither counts every click.
    """

    def __init__(self, repository: DatasetCounterRepository | None = None):
        self.repository = repository or DatasetCounterRepository()

    def counts(self, dataset_id: int) -> dict[str, int]:
        """``{"downloads": n, "views": n}`` for one dataset, zeros if it has none."""
        return self.counts_for_many([dataset_id])[dataset_id]

    def counts_for_many(self, dataset_ids: Iterable[int]) -> dict[int, dict[str, int]]:
        """Counts for several datasets with a fixed number of queries.

        Every requested id is in the result, with zeros when it has no
        activity, so callers can index it without checking.
        """
        ids = list(dict.fromkeys(dataset_ids))
        found = self.repository.counts(ids) if ids else {}
        return {
            dataset_id: {
                "downloads": int(found.get(dataset_id, {}).get("downloads", 0)),
                "views": int(found.get(dataset_id, {}).get("views", 0)),
            }
            for dataset_id in ids
        }


class MetricsService:
    """Turn repository rows into the dictionary consumed by the profile view."""

    def __init__(self, repository: MetricsRepository | None = None):
        self.repository = repository or MetricsRepository()

    def owner_summary(self, owner_id: int, today: datetime | None = None) -> dict:
        catalog = self.repository.owner_catalog_metrics(owner_id)
        activity = self.repository.owner_activity_metrics(owner_id)
        last_activity_at = as_utc(self.repository.last_activity(owner_id))
        activity_by_month = self.owner_activity_by_month(owner_id, today=today)

        views = activity["workflow_views"]
        downloads = activity["workflow_downloads"]
        activity_max = max(
            (max(row["downloads"], row["views"]) for row in activity_by_month),
            default=0,
        )

        return {
            **catalog,
            **activity,
            "download_rate": (downloads / views) if views else None,
            "last_activity_at": last_activity_at,
            "activity_by_month": activity_by_month,
            # A positive height divisor keeps the template free of zero checks.
            "activity_max": activity_max or 1,
        }

    def owner_activity_by_month(
        self,
        owner_id: int,
        months: int = 6,
        today: datetime | None = None,
    ) -> list[dict]:
        """Monthly dataset views/downloads for the last *months*, zero-filled.

        The series always ends in the current month and starts *months - 1*
        months earlier, so a quiet month is a row with zeros rather than a
        missing point (#63).
        """
        months = max(1, min(int(months), 24))
        today = as_utc(today or datetime.now(timezone.utc))
        first_index = today.year * 12 + (today.month - 1) - (months - 1)
        first_year, first_month_index = divmod(first_index, 12)
        since = datetime(first_year, first_month_index + 1, 1)

        totals = self.repository.owner_monthly_activity(owner_id, since)
        series = []
        for offset in range(months):
            year, month_index = divmod(first_index + offset, 12)
            month = month_index + 1
            counts = totals.get((year, month), {"downloads": 0, "views": 0})
            series.append(
                {
                    "month": f"{year:04d}-{month:02d}",
                    "label": f"{MONTH_LABELS[month - 1]} {year}",
                    "downloads": int(counts.get("downloads", 0)),
                    "views": int(counts.get("views", 0)),
                }
            )
        return series

    def workflows_for_owner(self, owner_id: int) -> list[dict]:
        return [
            {
                "id": row.id,
                "title": row.title,
                "published": row.dataset_doi is not None,
                "created_at": as_utc(row.created_at),
                "versions_total": int(row.versions_total or 0),
                "files_total": int(row.files_total or 0),
                "workflow_views": int(row.workflow_views or 0),
                "workflow_downloads": int(row.workflow_downloads or 0),
                "file_views": int(row.file_views or 0),
                "file_downloads": int(row.file_downloads or 0),
            }
            for row in self.repository.workflow_metrics(owner_id)
        ]
