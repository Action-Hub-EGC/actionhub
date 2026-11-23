import os

from splent_framework.configuration.configuration import uploads_folder_name
from splent_framework.services.BaseService import BaseService

from app import db
from app.features.auth.models import User
from app.features.dataset.models import BaseDataset
from app.features.hubfile.models import Hubfile
from app.features.hubfile.repositories import (
    HubfileDownloadRecordRepository,
    HubfileRepository,
    HubfileViewRecordRepository,
)


def uploads_root() -> str:
    """Absolute (or cwd-relative) root of every uploaded file.

    ``WORKING_DIR`` is the deployment root and ``uploads_folder_name()`` is
    normally relative to it. Tests and some deployments set an absolute
    ``UPLOADS_DIR``; that value wins as-is. Keeping this in one function
    removes the old split between ``WORKING_DIR/uploads`` and
    ``uploads_folder_name()`` (#37).
    """
    configured = uploads_folder_name()
    if os.path.isabs(configured):
        return configured
    return os.path.join(os.getenv("WORKING_DIR", ""), configured)


class HubfileService(BaseService):
    def __init__(self):
        super().__init__(HubfileRepository())
        self.hubfile_view_record_repository = HubfileViewRecordRepository()
        self.hubfile_download_record_repository = HubfileDownloadRecordRepository()

    def get_owner_user_by_hubfile(self, hubfile: Hubfile) -> User:
        if hubfile.workflow_version_id:
            dataset = self.get_dataset_by_hubfile(hubfile)
            return db.session.get(User, dataset.user_id) if dataset else None
        return self.repository.get_owner_user_by_hubfile(hubfile)

    def get_dataset_by_hubfile(self, hubfile: Hubfile) -> BaseDataset:
        if hubfile.workflow_version_id:
            from app.features.workflow.models import WorkflowVersion

            version = db.session.get(WorkflowVersion, hubfile.workflow_version_id)
            return db.session.get(BaseDataset, version.workflow_dataset_id) if version else None
        return self.repository.get_dataset_by_hubfile(hubfile)

    def dataset_directory(self, dataset: BaseDataset) -> str:
        """Old root of a dataset: ``uploads/user_<id>/dataset_<id>``."""
        return os.path.join(uploads_root(), f"user_{dataset.user_id}", f"dataset_{dataset.id}")

    def version_directory(self, dataset: BaseDataset, version=None) -> str:
        """Directory written by a version. Used for new files only.

        Version 1 of a dataset migrated from the old layout has no ``v1/`` yet;
        readers must use ``read_directory`` to fall back to the old root.
        """
        base = self.dataset_directory(dataset)
        if version is None or version.number is None:
            return base
        return os.path.join(base, f"v{version.number}")

    def read_directory(self, dataset: BaseDataset, version=None) -> str:
        """Directory to read a version from, with the pre-#37 compatibility path.

        Version 1 without a ``v1/`` folder lives in the old dataset root. That
        is what makes existing datasets and workflows keep downloading after
        the migration without moving their files.
        """
        directory = self.version_directory(dataset, version)
        if version is not None and version.number == 1 and not os.path.isdir(directory):
            return self.dataset_directory(dataset)
        return directory

    def get_dataset_version_by_hubfile(self, hubfile: Hubfile):
        """``DatasetVersion`` that owns the hubfile, or ``None`` on legacy rows."""
        if hubfile.workflow_version_id:
            from app.features.workflow.models import WorkflowVersion

            workflow_version = db.session.get(WorkflowVersion, hubfile.workflow_version_id)
            return workflow_version.dataset_version if workflow_version else None
        if hubfile.feature_model_id:
            from app.features.featuremodel.models import FeatureModel

            feature_model = db.session.get(FeatureModel, hubfile.feature_model_id)
            return feature_model.dataset_version if feature_model else None
        return None

    def get_path_by_hubfile(self, hubfile: Hubfile) -> str:
        dataset = self.get_dataset_by_hubfile(hubfile)
        version = self.get_dataset_version_by_hubfile(hubfile)
        return os.path.join(self.read_directory(dataset, version), hubfile.name)

    def total_hubfile_views(self) -> int:
        return self.hubfile_view_record_repository.total_hubfile_views()

    def total_hubfile_downloads(self) -> int:
        hubfile_download_record_repository = HubfileDownloadRecordRepository()
        return hubfile_download_record_repository.total_hubfile_downloads()

    def directory_for(self, hubfile: Hubfile) -> str:
        """Absolute filesystem directory holding the hubfile, for send_from_directory."""
        return os.path.dirname(self.get_path_by_hubfile(hubfile))

    def read_text(self, hubfile: Hubfile) -> str | None:
        """Read the file's text content. Returns ``None`` if the file is missing."""
        path = self.get_path_by_hubfile(hubfile)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return f.read()


class HubfileDownloadRecordService(BaseService):
    def __init__(self):
        super().__init__(HubfileDownloadRecordRepository())

    def record_download(self, user, file_id: int, cookie: str) -> None:
        """Record a download once per (user/anonymous, file, cookie) tuple."""
        from datetime import datetime, timezone

        user_id = user.id if user.is_authenticated else None
        if self.repository.find_by_user_file_cookie(user_id, file_id, cookie):
            return
        self.create(
            user_id=user_id,
            file_id=file_id,
            download_date=datetime.now(timezone.utc),
            download_cookie=cookie,
        )


class HubfileViewRecordService(BaseService):
    def __init__(self):
        super().__init__(HubfileViewRecordRepository())

    def record_view(self, user, file_id: int, cookie: str) -> None:
        """Record a view once per (user/anonymous, file, cookie) tuple."""
        from datetime import datetime, timezone

        user_id = user.id if user.is_authenticated else None
        if self.repository.find_by_user_file_cookie(user_id, file_id, cookie):
            return
        self.create(
            user_id=user_id,
            file_id=file_id,
            view_date=datetime.now(timezone.utc),
            view_cookie=cookie,
        )
