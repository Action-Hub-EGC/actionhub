import logging
from datetime import datetime, timezone
from typing import Optional

from splent_framework.repositories.BaseRepository import BaseRepository
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError

from app.features.dataset.models import (
    Author,
    BaseDataset,
    DatasetVersion,
    DOIMapping,
    DSDownloadRecord,
    DSMetaData,
    DSViewRecord,
    UVLDataset,
)

logger = logging.getLogger(__name__)


def _find(repository: BaseRepository, key: dict):
    # filter_by(user_id=None) becomes "user_id IS NULL", so anonymous rows match.
    return repository.model.query.filter_by(**key).first()


def _create_once(repository: BaseRepository, key: dict, **values) -> bool:
    """Insert the record identified by *key* unless it already exists.

    Returns True if this call inserted it. The lookup avoids an exception in
    the usual case; the unique index settles the race in which two concurrent
    requests both miss the lookup: the second insert fails and counts as
    already recorded.

    Call it with no other change pending in the session: recovering from the
    failed insert rolls the whole session back, which would discard it too.
    """
    if _find(repository, key):
        return False
    try:
        repository.create(**key, **values)
    except IntegrityError:
        repository.session.rollback()
        if _find(repository, key) is None:
            raise  # Not our duplicate: a missing dataset or user, for example.
        return False
    return True


class AuthorRepository(BaseRepository):
    def __init__(self):
        super().__init__(Author)


class DSDownloadRecordRepository(BaseRepository):
    def __init__(self):
        super().__init__(DSDownloadRecord)

    def total_dataset_downloads(self) -> int:
        # Same rows as DatasetCounterService: a record without a dataset never counts.
        return self.model.query.filter(self.model.dataset_id.isnot(None)).count()

    def find_by_user_dataset_cookie(self, user_id, dataset_id: int, cookie: str):
        return self.model.query.filter_by(user_id=user_id, dataset_id=dataset_id, download_cookie=cookie).first()

    def record_once(self, user_id: Optional[int], dataset_id: int, cookie: str) -> bool:
        key = {"user_id": user_id, "dataset_id": dataset_id, "download_cookie": cookie}
        return _create_once(self, key, download_date=datetime.now(timezone.utc))


class DSMetaDataRepository(BaseRepository):
    def __init__(self):
        super().__init__(DSMetaData)

    def filter_by_doi(self, doi: str) -> Optional[DSMetaData]:
        return self.model.query.filter_by(dataset_doi=doi).first()


class DatasetVersionRepository(BaseRepository):
    def __init__(self):
        super().__init__(DatasetVersion)

    def get_by_dataset_and_number(self, dataset_id: int, number: int) -> Optional[DatasetVersion]:
        return self.model.query.filter_by(dataset_id=dataset_id, number=number).first()

    def next_number(self, dataset_id: int) -> int:
        last = self.model.query.filter_by(dataset_id=dataset_id).order_by(self.model.number.desc()).first()
        return (last.number if last else 0) + 1


class DSViewRecordRepository(BaseRepository):
    def __init__(self):
        super().__init__(DSViewRecord)

    def total_dataset_views(self) -> int:
        # Same rows as DatasetCounterService: a record without a dataset never counts.
        return self.model.query.filter(self.model.dataset_id.isnot(None)).count()

    def record_once(self, user_id: Optional[int], dataset_id: int, cookie: str) -> bool:
        key = {"user_id": user_id, "dataset_id": dataset_id, "view_cookie": cookie}
        return _create_once(self, key, view_date=datetime.now(timezone.utc))


class DataSetRepository(BaseRepository):
    """UVL dataset repository.

    It keeps the historical name and creates ``UVLDataset`` rows by default.
    The per-user listing of the profile (``paginate_for_user`` and
    ``count_for_user``) reads ``BaseDataset`` so every dataset type shows up;
    the other reads stay UVL-only for ``/dataset/list`` and the UVL pages.
    """

    def __init__(self):
        super().__init__(UVLDataset)

    def get_synchronized(self, current_user_id: int) -> BaseDataset:
        return (
            self.model.query.join(DSMetaData)
            .filter(BaseDataset.user_id == current_user_id, DSMetaData.dataset_doi.isnot(None))
            .order_by(self.model.created_at.desc())
            .all()
        )

    def get_unsynchronized(self, current_user_id: int) -> BaseDataset:
        return (
            self.model.query.join(DSMetaData)
            .filter(BaseDataset.user_id == current_user_id, DSMetaData.dataset_doi.is_(None))
            .order_by(self.model.created_at.desc())
            .all()
        )

    def get_unsynchronized_dataset(self, current_user_id: int, dataset_id: int) -> BaseDataset:
        return (
            self.model.query.join(DSMetaData)
            .filter(
                BaseDataset.user_id == current_user_id, BaseDataset.id == dataset_id, DSMetaData.dataset_doi.is_(None)
            )
            .first()
        )

    def count_synchronized_datasets(self):
        return self.model.query.join(DSMetaData).filter(DSMetaData.dataset_doi.isnot(None)).count()

    def count_unsynchronized_datasets(self):
        return self.model.query.join(DSMetaData).filter(DSMetaData.dataset_doi.is_(None)).count()

    def paginate_for_user(self, user_id: int, page: int, per_page: int):
        """Datasets of every type owned by *user_id*, newest first."""
        return (
            BaseDataset.query.filter(BaseDataset.user_id == user_id)
            .order_by(BaseDataset.created_at.desc(), BaseDataset.id.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )

    def count_for_user(self, user_id: int) -> int:
        """Datasets of every type owned by *user_id*, like the profile metrics."""
        return BaseDataset.query.filter(BaseDataset.user_id == user_id).count()

    def latest_synchronized(self):
        return (
            self.model.query.join(DSMetaData)
            .filter(DSMetaData.dataset_doi.isnot(None))
            .order_by(desc(self.model.id))
            .limit(5)
            .all()
        )


class DOIMappingRepository(BaseRepository):
    def __init__(self):
        super().__init__(DOIMapping)

    def get_new_doi(self, old_doi: str) -> str:
        return self.model.query.filter_by(dataset_doi_old=old_doi).first()
