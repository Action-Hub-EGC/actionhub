from typing import Iterable

from app.features.metrics.repositories import DatasetCounterRepository, MetricsRepository
from app.features.metrics.utils import as_utc


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

    def owner_summary(self, owner_id: int) -> dict:
        catalog = self.repository.owner_catalog_metrics(owner_id)
        activity = self.repository.owner_activity_metrics(owner_id)
        last_activity_at = as_utc(self.repository.last_activity(owner_id))

        views = activity["workflow_views"]
        downloads = activity["workflow_downloads"]

        return {
            **catalog,
            **activity,
            "download_rate": (downloads / views) if views else None,
            "last_activity_at": last_activity_at,
        }

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
