from datetime import datetime
from enum import Enum

from flask import request
from sqlalchemy import Computed
from sqlalchemy import Enum as SQLAlchemyEnum

from app import db

# ``user_id`` is NULL for anonymous visitors, and MariaDB never treats two
# NULLs as equal in a unique index. The records deduplicate on this stored
# column instead: 0 stands for "anonymous", which no real user id can be.
USER_KEY_EXPRESSION = "COALESCE(user_id, 0)"


class PublicationType(Enum):
    NONE = "none"
    ANNOTATION_COLLECTION = "annotationcollection"
    BOOK = "book"
    BOOK_SECTION = "section"
    CONFERENCE_PAPER = "conferencepaper"
    DATA_MANAGEMENT_PLAN = "datamanagementplan"
    JOURNAL_ARTICLE = "article"
    PATENT = "patent"
    PREPRINT = "preprint"
    PROJECT_DELIVERABLE = "deliverable"
    PROJECT_MILESTONE = "milestone"
    PROPOSAL = "proposal"
    REPORT = "report"
    SOFTWARE_DOCUMENTATION = "softwaredocumentation"
    TAXONOMIC_TREATMENT = "taxonomictreatment"
    TECHNICAL_NOTE = "technicalnote"
    THESIS = "thesis"
    WORKING_PAPER = "workingpaper"
    OTHER = "other"


class Author(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    affiliation = db.Column(db.String(120))
    orcid = db.Column(db.String(120))
    ds_meta_data_id = db.Column(db.Integer, db.ForeignKey("ds_meta_data.id"))
    fm_meta_data_id = db.Column(db.Integer, db.ForeignKey("fm_meta_data.id"))

    def to_dict(self):
        return {"name": self.name, "affiliation": self.affiliation, "orcid": self.orcid}


class DSMetrics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number_of_models = db.Column(db.String(120))
    number_of_features = db.Column(db.String(120))

    def __repr__(self):
        return f"DSMetrics<models={self.number_of_models}, features={self.number_of_features}>"


class DSMetaData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    deposition_id = db.Column(db.Integer)
    # Concept identity shared by every version of the dataset (#36). Zenodo
    # calls the numeric id ``conceptrecid`` and the DOI ``conceptdoi``. They
    # belong to the dataset, not to a version, and stay NULL for datasets
    # published before this column existed until they are recovered.
    conceptrecid = db.Column(db.Integer)
    concept_doi = db.Column(db.String(120))
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    publication_type = db.Column(SQLAlchemyEnum(PublicationType), nullable=False)
    publication_doi = db.Column(db.String(120))
    dataset_doi = db.Column(db.String(120))
    tags = db.Column(db.String(120))
    ds_metrics_id = db.Column(db.Integer, db.ForeignKey("ds_metrics.id"))
    ds_metrics = db.relationship("DSMetrics", uselist=False, backref="ds_meta_data", cascade="all, delete")
    authors = db.relationship("Author", backref="ds_meta_data", lazy=True, cascade="all, delete")


class BaseDataset(db.Model):
    """Common part of every dataset type in ActionHub.

    The table keeps the historical name ``data_set`` to avoid a data
    migration. ``type`` is the single-table inheritance discriminator:
    existing rows are ``uvl``; workflow rows will be ``workflow``.
    """

    __tablename__ = "data_set"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    ds_meta_data_id = db.Column(db.Integer, db.ForeignKey("ds_meta_data.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    type = db.Column(db.String(20), nullable=False, default="uvl", server_default="uvl")

    ds_meta_data = db.relationship("DSMetaData", backref=db.backref("data_set", uselist=False))
    dataset_versions = db.relationship(
        "DatasetVersion",
        backref="dataset",
        lazy=True,
        cascade="all, delete",
        order_by="DatasetVersion.number",
    )

    __mapper_args__ = {"polymorphic_on": type, "polymorphic_identity": "base"}

    def name(self):
        return self.ds_meta_data.title

    def latest_dataset_version(self):
        """Highest version number, published or draft."""
        return self.dataset_versions[-1] if self.dataset_versions else None

    def latest_published_dataset_version(self):
        """Highest version with a DOI; ``None`` before the first publication."""
        published = [version for version in self.dataset_versions if version.doi]
        return published[-1] if published else None

    def files_for_version(self, version=None):
        """Files of ``version``, or of the latest published version by default."""
        version = version or self.latest_published_dataset_version()
        return version.files() if version is not None else []

    def files(self):
        """Files that belong to the dataset. Subclasses override this."""
        return []

    def delete(self):
        db.session.delete(self)
        db.session.commit()

    def get_cleaned_publication_type(self):
        return self.ds_meta_data.publication_type.name.replace("_", " ").title()

    def get_zenodo_url(self):
        """Public record URL of the latest published deposition (#32).

        The base is configured (``ZENODO_RECORD_URL``) or derived from
        ``ZENODO_API_URL``: fakenodo links point at fakenodo, Zenodo links at
        Zenodo. A dataset without a DOI or a deposition has no record.
        """
        if self.ds_meta_data.dataset_doi and self.ds_meta_data.deposition_id:
            from app.features.zenodo.urls import record_url

            return record_url(self.ds_meta_data.deposition_id)
        return None

    def get_files_count(self):
        return len(self.files())

    def get_file_total_size(self):
        return sum(file.size for file in self.files())

    def get_file_total_size_for_human(self):
        from app.features.dataset.services import SizeService

        return SizeService().get_human_readable_size(self.get_file_total_size())

    def get_public_doi(self):
        from app.features.dataset.services import DataSetService

        return DataSetService().get_public_doi(self)

    def get_uvlhub_doi(self):
        """Backward-compatible alias for ``get_public_doi``."""
        return self.get_public_doi()

    def to_dict(self):
        return {
            "title": self.ds_meta_data.title,
            "id": self.id,
            "created_at": self.created_at,
            "created_at_timestamp": int(self.created_at.timestamp()),
            "description": self.ds_meta_data.description,
            "authors": [author.to_dict() for author in self.ds_meta_data.authors],
            "publication_type": self.get_cleaned_publication_type(),
            "publication_doi": self.ds_meta_data.publication_doi,
            "dataset_doi": self.ds_meta_data.dataset_doi,
            "tags": self.ds_meta_data.tags.split(",") if self.ds_meta_data.tags else [],
            "url": self.get_public_doi(),
            "download": f'{request.host_url.rstrip("/")}/dataset/download/{self.id}',
            "zenodo": self.get_zenodo_url(),
            "files": [file.to_dict() for file in self.files()],
            "files_count": self.get_files_count(),
            "total_size_in_bytes": self.get_file_total_size(),
            "total_size_in_human_format": self.get_file_total_size_for_human(),
        }

    def __repr__(self):
        return f"{self.__class__.__name__}<{self.id}>"


class DatasetVersion(db.Model):
    """One major version of a dataset (#36).

    The dataset row is the identity users see in the catalogue, the explorer
    and the metrics. A version holds the deposition, DOI and files of one
    publication, so publishing a new one never overwrites the previous DOI or
    its files. UVL and workflow datasets share this table; the type-specific
    content hangs from ``FeatureModel`` or ``WorkflowVersion``.
    """

    __tablename__ = "dataset_version"
    __table_args__ = (db.UniqueConstraint("dataset_id", "number", name="uq_dataset_version_number"),)

    id = db.Column(db.Integer, primary_key=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey("data_set.id"), nullable=False)
    number = db.Column(db.Integer, nullable=False)
    deposition_id = db.Column(db.Integer)
    doi = db.Column(db.String(120))
    change_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    published_at = db.Column(db.DateTime)

    feature_models = db.relationship("FeatureModel", backref="dataset_version", lazy=True)
    workflow_version = db.relationship(
        "WorkflowVersion",
        backref=db.backref("dataset_version", uselist=False),
        uselist=False,
    )

    def files(self):
        """Files that belong to this version, for either dataset type."""
        if self.workflow_version is not None:
            return list(self.workflow_version.files)
        return [file for feature_model in self.feature_models for file in feature_model.files]

    def is_published(self):
        return self.doi is not None

    def __repr__(self):
        return f"DatasetVersion<dataset={self.dataset_id}, number={self.number}>"


class UVLDataset(BaseDataset):
    """Dataset whose versions are UVL feature models."""

    __mapper_args__ = {"polymorphic_identity": "uvl"}

    feature_models = db.relationship("FeatureModel", backref="data_set", lazy=True, cascade="all, delete")

    def files(self):
        return [file for fm in self.feature_models for file in fm.files]


# Backward-compatible name: existing imports, seeders and tests keep working
# and create UVL datasets by default.
DataSet = UVLDataset


class DSDownloadRecord(db.Model):
    """One row per (user or anonymous, dataset, browser cookie): decision #66."""

    __table_args__ = (
        db.UniqueConstraint("user_key", "dataset_id", "download_cookie", name="uq_ds_download_record_once"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    user_key = db.Column(db.Integer, Computed(USER_KEY_EXPRESSION, persisted=True))
    dataset_id = db.Column(db.Integer, db.ForeignKey("data_set.id"))
    download_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    download_cookie = db.Column(db.String(36), nullable=False)  # Assuming UUID4 strings

    def __repr__(self):
        return (
            f"<Download id={self.id} "
            f"dataset_id={self.dataset_id} "
            f"date={self.download_date} "
            f"cookie={self.download_cookie}>"
        )


class DSViewRecord(db.Model):
    """One row per (user or anonymous, dataset, browser cookie), like downloads."""

    __table_args__ = (db.UniqueConstraint("user_key", "dataset_id", "view_cookie", name="uq_ds_view_record_once"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    user_key = db.Column(db.Integer, Computed(USER_KEY_EXPRESSION, persisted=True))
    dataset_id = db.Column(db.Integer, db.ForeignKey("data_set.id"))
    view_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    view_cookie = db.Column(db.String(36), nullable=False)  # Assuming UUID4 strings

    def __repr__(self):
        return f"<View id={self.id} dataset_id={self.dataset_id} date={self.view_date} cookie={self.view_cookie}>"


class DOIMapping(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dataset_doi_old = db.Column(db.String(120))
    dataset_doi_new = db.Column(db.String(120))
