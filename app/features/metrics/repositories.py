from datetime import datetime
from typing import Optional

from sqlalchemy import case, desc, func

from app import db
from app.features.dataset.models import DataSet, DSDownloadRecord, DSMetaData, DSViewRecord
from app.features.featuremodel.models import FeatureModel
from app.features.hubfile.models import Hubfile, HubfileDownloadRecord, HubfileViewRecord
from app.features.metrics.utils import as_utc


class MetricsRepository:
    """Read-only aggregations over the existing catalog and activity tables.

    Every query joins the record to its live resource and filters by
    ``DataSet.user_id``. The ``user_id`` stored in a view/download record is
    the visitor, never the owner, so it must not be used for attribution.
    """

    def owner_catalog_metrics(self, owner_id: int) -> dict:
        counts = (
            db.session.query(
                func.count(DataSet.id).label("workflows_total"),
                func.coalesce(
                    func.sum(case((DSMetaData.dataset_doi.isnot(None), 1), else_=0)),
                    0,
                ).label("published_total"),
            )
            .join(DSMetaData, DataSet.ds_meta_data_id == DSMetaData.id)
            .filter(DataSet.user_id == owner_id)
            .one()
        )

        versions_files = (
            db.session.query(
                func.count(func.distinct(FeatureModel.id)).label("versions_total"),
                func.count(Hubfile.id).label("files_total"),
                func.coalesce(func.sum(Hubfile.size), 0).label("size_total_bytes"),
            )
            .select_from(DataSet)
            .join(FeatureModel, FeatureModel.data_set_id == DataSet.id)
            .outerjoin(Hubfile, Hubfile.feature_model_id == FeatureModel.id)
            .filter(DataSet.user_id == owner_id)
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
            .join(DataSet, DSViewRecord.dataset_id == DataSet.id)
            .filter(DataSet.user_id == owner_id)
            .scalar()
        )
        workflow_downloads = (
            db.session.query(func.count(DSDownloadRecord.id))
            .join(DataSet, DSDownloadRecord.dataset_id == DataSet.id)
            .filter(DataSet.user_id == owner_id)
            .scalar()
        )
        file_views = (
            db.session.query(func.count(HubfileViewRecord.id))
            .join(Hubfile, HubfileViewRecord.file_id == Hubfile.id)
            .join(FeatureModel, Hubfile.feature_model_id == FeatureModel.id)
            .join(DataSet, FeatureModel.data_set_id == DataSet.id)
            .filter(DataSet.user_id == owner_id)
            .scalar()
        )
        file_downloads = (
            db.session.query(func.count(HubfileDownloadRecord.id))
            .join(Hubfile, HubfileDownloadRecord.file_id == Hubfile.id)
            .join(FeatureModel, Hubfile.feature_model_id == FeatureModel.id)
            .join(DataSet, FeatureModel.data_set_id == DataSet.id)
            .filter(DataSet.user_id == owner_id)
            .scalar()
        )
        unique_visitors = (
            db.session.query(func.count(func.distinct(DSViewRecord.view_cookie)))
            .join(DataSet, DSViewRecord.dataset_id == DataSet.id)
            .filter(DataSet.user_id == owner_id, DSViewRecord.view_cookie.isnot(None))
            .scalar()
        )

        return {
            "workflow_views": int(workflow_views or 0),
            "workflow_downloads": int(workflow_downloads or 0),
            "file_views": int(file_views or 0),
            "file_downloads": int(file_downloads or 0),
            "unique_visitors": int(unique_visitors or 0),
        }

    def last_activity(self, owner_id: int) -> Optional[datetime]:
        candidates = [
            db.session.query(func.max(DSViewRecord.view_date))
            .join(DataSet, DSViewRecord.dataset_id == DataSet.id)
            .filter(DataSet.user_id == owner_id)
            .scalar(),
            db.session.query(func.max(DSDownloadRecord.download_date))
            .join(DataSet, DSDownloadRecord.dataset_id == DataSet.id)
            .filter(DataSet.user_id == owner_id)
            .scalar(),
            db.session.query(func.max(HubfileViewRecord.view_date))
            .join(Hubfile, HubfileViewRecord.file_id == Hubfile.id)
            .join(FeatureModel, Hubfile.feature_model_id == FeatureModel.id)
            .join(DataSet, FeatureModel.data_set_id == DataSet.id)
            .filter(DataSet.user_id == owner_id)
            .scalar(),
            db.session.query(func.max(HubfileDownloadRecord.download_date))
            .join(Hubfile, HubfileDownloadRecord.file_id == Hubfile.id)
            .join(FeatureModel, Hubfile.feature_model_id == FeatureModel.id)
            .join(DataSet, FeatureModel.data_set_id == DataSet.id)
            .filter(DataSet.user_id == owner_id)
            .scalar(),
        ]
        # MariaDB hands back naive datetimes; they are all UTC by convention.
        normalized = [as_utc(value) for value in candidates]
        return max((value for value in normalized if value is not None), default=None)

    def workflow_metrics(self, owner_id: int) -> list:
        dataset_views = (
            db.session.query(
                DSViewRecord.dataset_id.label("dataset_id"),
                func.count(DSViewRecord.id).label("views"),
            )
            .group_by(DSViewRecord.dataset_id)
            .subquery()
        )
        dataset_downloads = (
            db.session.query(
                DSDownloadRecord.dataset_id.label("dataset_id"),
                func.count(DSDownloadRecord.id).label("downloads"),
            )
            .group_by(DSDownloadRecord.dataset_id)
            .subquery()
        )
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
                DataSet.id.label("id"),
                DSMetaData.title.label("title"),
                DSMetaData.dataset_doi.label("dataset_doi"),
                DataSet.created_at.label("created_at"),
                func.count(func.distinct(FeatureModel.id)).label("versions_total"),
                func.count(func.distinct(Hubfile.id)).label("files_total"),
                dataset_views_count.label("workflow_views"),
                dataset_downloads_count.label("workflow_downloads"),
                file_views_count.label("file_views"),
                file_downloads_count.label("file_downloads"),
            )
            .join(DSMetaData, DataSet.ds_meta_data_id == DSMetaData.id)
            .outerjoin(FeatureModel, FeatureModel.data_set_id == DataSet.id)
            .outerjoin(Hubfile, Hubfile.feature_model_id == FeatureModel.id)
            .outerjoin(dataset_views, dataset_views.c.dataset_id == DataSet.id)
            .outerjoin(dataset_downloads, dataset_downloads.c.dataset_id == DataSet.id)
            .outerjoin(file_views, file_views.c.dataset_id == DataSet.id)
            .outerjoin(file_downloads, file_downloads.c.dataset_id == DataSet.id)
            .filter(DataSet.user_id == owner_id)
            .group_by(
                DataSet.id,
                DSMetaData.title,
                DSMetaData.dataset_doi,
                DataSet.created_at,
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
