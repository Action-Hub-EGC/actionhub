from datetime import datetime
from typing import Iterable, Optional

from sqlalchemy import case, desc, func

from app import db
from app.features.dataset.models import BaseDataset, DSDownloadRecord, DSMetaData, DSViewRecord
from app.features.featuremodel.models import FeatureModel
from app.features.hubfile.models import Hubfile, HubfileDownloadRecord, HubfileViewRecord
from app.features.metrics.utils import as_utc


class DatasetCounterRepository:
    """Per-dataset download and view counts (#67).

    A count is the number of ``DSDownloadRecord`` or ``DSViewRecord`` rows of
    the dataset. Each row is already one (user or anonymous, dataset, browser
    cookie), so the count follows decision #66 without further deduplication.
    Rows without ``dataset_id`` never match a dataset and are not counted.
    Every per-dataset count in the app is built from these two subqueries.
    """

    @staticmethod
    def downloads_by_dataset():
        return (
            db.session.query(
                DSDownloadRecord.dataset_id.label("dataset_id"),
                func.count(DSDownloadRecord.id).label("downloads"),
            )
            .filter(DSDownloadRecord.dataset_id.isnot(None))
            .group_by(DSDownloadRecord.dataset_id)
            .subquery()
        )

    @staticmethod
    def views_by_dataset():
        return (
            db.session.query(
                DSViewRecord.dataset_id.label("dataset_id"),
                func.count(DSViewRecord.id).label("views"),
            )
            .filter(DSViewRecord.dataset_id.isnot(None))
            .group_by(DSViewRecord.dataset_id)
            .subquery()
        )

    def counts(self, dataset_ids: Iterable[int]) -> dict[int, dict[str, int]]:
        """Counts of the given datasets that have any activity, in two queries."""
        ids = list(dataset_ids)
        if not ids:
            return {}
        downloads = self.downloads_by_dataset()
        views = self.views_by_dataset()
        result: dict[int, dict[str, int]] = {}
        for row in db.session.query(downloads).filter(downloads.c.dataset_id.in_(ids)):
            result.setdefault(row.dataset_id, {})["downloads"] = int(row.downloads)
        for row in db.session.query(views).filter(views.c.dataset_id.in_(ids)):
            result.setdefault(row.dataset_id, {})["views"] = int(row.views)
        return result


class MetricsRepository:
    """Read-only aggregations over the existing catalog and activity tables.

    Every query joins the record to its live resource and filters by
    ``BaseDataset.user_id``. The ``user_id`` stored in a view/download record is
    the visitor, never the owner, so it must not be used for attribution.
    """

    def owner_catalog_metrics(self, owner_id: int) -> dict:
        counts = (
            db.session.query(
                func.count(BaseDataset.id).label("workflows_total"),
                func.coalesce(
                    func.sum(case((DSMetaData.dataset_doi.isnot(None), 1), else_=0)),
                    0,
                ).label("published_total"),
            )
            .join(DSMetaData, BaseDataset.ds_meta_data_id == DSMetaData.id)
            .filter(BaseDataset.user_id == owner_id)
            .one()
        )

        versions_files = (
            db.session.query(
                func.count(func.distinct(FeatureModel.id)).label("versions_total"),
                func.count(Hubfile.id).label("files_total"),
                func.coalesce(func.sum(Hubfile.size), 0).label("size_total_bytes"),
            )
            .select_from(BaseDataset)
            .join(FeatureModel, FeatureModel.data_set_id == BaseDataset.id)
            .outerjoin(Hubfile, Hubfile.feature_model_id == FeatureModel.id)
            .filter(BaseDataset.user_id == owner_id)
            .one()
        )

        workflows_total = int(counts.workflows_total or 0)
        published_total = int(counts.published_total or 0)

        return {
            "workflows_total": workflows_total,
            "published_total": published_total,
            "draft_total": workflows_total - published_total,
            "versions_total": int(versions_files.versions_total or 0),
            "files_total": int(versions_files.files_total or 0),
            "size_total_bytes": int(versions_files.size_total_bytes or 0),
        }

    def owner_activity_metrics(self, owner_id: int) -> dict:
        workflow_views = (
            db.session.query(func.count(DSViewRecord.id))
            .join(BaseDataset, DSViewRecord.dataset_id == BaseDataset.id)
            .filter(BaseDataset.user_id == owner_id)
            .scalar()
        )
        workflow_downloads = (
            db.session.query(func.count(DSDownloadRecord.id))
            .join(BaseDataset, DSDownloadRecord.dataset_id == BaseDataset.id)
            .filter(BaseDataset.user_id == owner_id)
            .scalar()
        )
        file_views = (
            db.session.query(func.count(HubfileViewRecord.id))
            .join(Hubfile, HubfileViewRecord.file_id == Hubfile.id)
            .join(FeatureModel, Hubfile.feature_model_id == FeatureModel.id)
            .join(BaseDataset, FeatureModel.data_set_id == BaseDataset.id)
            .filter(BaseDataset.user_id == owner_id)
            .scalar()
        )
        file_downloads = (
            db.session.query(func.count(HubfileDownloadRecord.id))
            .join(Hubfile, HubfileDownloadRecord.file_id == Hubfile.id)
            .join(FeatureModel, Hubfile.feature_model_id == FeatureModel.id)
            .join(BaseDataset, FeatureModel.data_set_id == BaseDataset.id)
            .filter(BaseDataset.user_id == owner_id)
            .scalar()
        )
        unique_visitors = (
            db.session.query(func.count(func.distinct(DSViewRecord.view_cookie)))
            .join(BaseDataset, DSViewRecord.dataset_id == BaseDataset.id)
            .filter(BaseDataset.user_id == owner_id, DSViewRecord.view_cookie.isnot(None))
            .scalar()
        )

        return {
            "workflow_views": int(workflow_views or 0),
            "workflow_downloads": int(workflow_downloads or 0),
            "file_views": int(file_views or 0),
            "file_downloads": int(file_downloads or 0),
            "unique_visitors": int(unique_visitors or 0),
        }

    def owner_monthly_activity(self, owner_id: int, since: datetime) -> dict[tuple[int, int], dict[str, int]]:
        """Dataset views and downloads per ``(year, month)`` since *since*.

        Only records linked to a dataset owned by *owner_id* count. The record's
        own ``user_id`` is the visitor, not the owner, so the join through
        ``BaseDataset`` is what attributes the activity. Months without rows
        are absent here; the service fills them with zero (#63).
        """
        totals: dict[tuple[int, int], dict[str, int]] = {}
        for model, date_column, metric in (
            (DSDownloadRecord, DSDownloadRecord.download_date, "downloads"),
            (DSViewRecord, DSViewRecord.view_date, "views"),
        ):
            year = func.extract("year", date_column)
            month = func.extract("month", date_column)
            rows = (
                db.session.query(
                    year.label("year"),
                    month.label("month"),
                    func.count(model.id).label("total"),
                )
                .join(BaseDataset, model.dataset_id == BaseDataset.id)
                .filter(BaseDataset.user_id == owner_id, date_column >= since)
                .group_by(year, month)
                .all()
            )
            for row in rows:
                key = (int(row.year), int(row.month))
                totals.setdefault(key, {"downloads": 0, "views": 0})[metric] = int(row.total)
        return totals

    def last_activity(self, owner_id: int) -> Optional[datetime]:
        candidates = [
            db.session.query(func.max(DSViewRecord.view_date))
            .join(BaseDataset, DSViewRecord.dataset_id == BaseDataset.id)
            .filter(BaseDataset.user_id == owner_id)
            .scalar(),
            db.session.query(func.max(DSDownloadRecord.download_date))
            .join(BaseDataset, DSDownloadRecord.dataset_id == BaseDataset.id)
            .filter(BaseDataset.user_id == owner_id)
            .scalar(),
            db.session.query(func.max(HubfileViewRecord.view_date))
            .join(Hubfile, HubfileViewRecord.file_id == Hubfile.id)
            .join(FeatureModel, Hubfile.feature_model_id == FeatureModel.id)
            .join(BaseDataset, FeatureModel.data_set_id == BaseDataset.id)
            .filter(BaseDataset.user_id == owner_id)
            .scalar(),
            db.session.query(func.max(HubfileDownloadRecord.download_date))
            .join(Hubfile, HubfileDownloadRecord.file_id == Hubfile.id)
            .join(FeatureModel, Hubfile.feature_model_id == FeatureModel.id)
            .join(BaseDataset, FeatureModel.data_set_id == BaseDataset.id)
            .filter(BaseDataset.user_id == owner_id)
            .scalar(),
        ]
        # MariaDB hands back naive datetimes; they are all UTC by convention.
        normalized = [as_utc(value) for value in candidates]
        return max((value for value in normalized if value is not None), default=None)

    def workflow_metrics(self, owner_id: int) -> list:
        dataset_views = DatasetCounterRepository.views_by_dataset()
        dataset_downloads = DatasetCounterRepository.downloads_by_dataset()
        file_views = (
            db.session.query(
                FeatureModel.data_set_id.label("dataset_id"),
                func.count(HubfileViewRecord.id).label("file_views"),
            )
            .join(Hubfile, HubfileViewRecord.file_id == Hubfile.id)
            .join(FeatureModel, Hubfile.feature_model_id == FeatureModel.id)
            .group_by(FeatureModel.data_set_id)
            .subquery()
        )
        file_downloads = (
            db.session.query(
                FeatureModel.data_set_id.label("dataset_id"),
                func.count(HubfileDownloadRecord.id).label("file_downloads"),
            )
            .join(Hubfile, HubfileDownloadRecord.file_id == Hubfile.id)
            .join(FeatureModel, Hubfile.feature_model_id == FeatureModel.id)
            .group_by(FeatureModel.data_set_id)
            .subquery()
        )

        dataset_views_count = func.coalesce(dataset_views.c.views, 0)
        dataset_downloads_count = func.coalesce(dataset_downloads.c.downloads, 0)
        file_views_count = func.coalesce(file_views.c.file_views, 0)
        file_downloads_count = func.coalesce(file_downloads.c.file_downloads, 0)

        return (
            db.session.query(
                BaseDataset.id.label("id"),
                DSMetaData.title.label("title"),
                DSMetaData.dataset_doi.label("dataset_doi"),
                BaseDataset.created_at.label("created_at"),
                func.count(func.distinct(FeatureModel.id)).label("versions_total"),
                func.count(func.distinct(Hubfile.id)).label("files_total"),
                dataset_views_count.label("workflow_views"),
                dataset_downloads_count.label("workflow_downloads"),
                file_views_count.label("file_views"),
                file_downloads_count.label("file_downloads"),
            )
            .join(DSMetaData, BaseDataset.ds_meta_data_id == DSMetaData.id)
            .outerjoin(FeatureModel, FeatureModel.data_set_id == BaseDataset.id)
            .outerjoin(Hubfile, Hubfile.feature_model_id == FeatureModel.id)
            .outerjoin(dataset_views, dataset_views.c.dataset_id == BaseDataset.id)
            .outerjoin(dataset_downloads, dataset_downloads.c.dataset_id == BaseDataset.id)
            .outerjoin(file_views, file_views.c.dataset_id == BaseDataset.id)
            .outerjoin(file_downloads, file_downloads.c.dataset_id == BaseDataset.id)
            .filter(BaseDataset.user_id == owner_id)
            .group_by(
                BaseDataset.id,
                DSMetaData.title,
                DSMetaData.dataset_doi,
                BaseDataset.created_at,
                dataset_views.c.views,
                dataset_downloads.c.downloads,
                file_views.c.file_views,
                file_downloads.c.file_downloads,
            )
            .order_by(
                desc(dataset_downloads_count),
                desc(dataset_views_count),
                DSMetaData.title.asc(),
            )
            .all()
        )
