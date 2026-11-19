from app.features.metrics.repositories import MetricsRepository
from app.features.metrics.utils import as_utc


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
