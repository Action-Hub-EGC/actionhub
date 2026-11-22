"""Workflow dataset type.

``WorkflowDataset`` is a single-table-inheritance subclass of ``BaseDataset``:
its columns live in ``data_set`` and the discriminator is ``type='workflow'``.
``WorkflowVersion`` is a separate table because a workflow can have many
versions and each version owns its manifest, workflow YAML and package files.
"""

import json
from datetime import datetime

from app import db
from app.features.dataset.models import BaseDataset


class ValidationStatus:
    """Values stored in ``WorkflowDataset.validation_status``."""

    DRAFT = "draft"
    VALIDATED = "validated"
    FAILED = "failed"


class WorkflowDataset(BaseDataset):
    """A GitHub Actions workflow published in ActionHub."""

    __mapper_args__ = {"polymorphic_identity": "workflow"}

    manifest_json = db.Column(db.Text)
    validation_status = db.Column(db.String(20), nullable=False, default="draft")
    security_score = db.Column(db.Integer)
    grade = db.Column(db.String(1))
    actionlint_version = db.Column(db.String(40))
    package_format = db.Column(db.String(20))

    versions = db.relationship("WorkflowVersion", backref="workflow_dataset", lazy=True, cascade="all, delete")

    def files(self):
        return [file for version in self.versions for file in version.files]

    def latest_version(self):
        return max(self.versions, key=lambda version: version.created_at, default=None)

    def workflow_metadata(self):
        """Metadata of the latest version, for listings and the detail page."""
        latest = self.latest_version()
        return latest.workflow_metadata if latest else None


class WorkflowVersion(db.Model):
    """One published version of a workflow package."""

    __tablename__ = "workflow_version"

    id = db.Column(db.Integer, primary_key=True)
    workflow_dataset_id = db.Column(db.Integer, db.ForeignKey("data_set.id"), nullable=False)
    manifest_json = db.Column(db.Text, nullable=False)
    workflow_yaml = db.Column(db.Text, nullable=False)
    metadata_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    files = db.relationship("Hubfile", backref="workflow_version", lazy=True, cascade="all, delete")

    @property
    def workflow_metadata(self):
        """Extracted metadata (#17) as a dict, or ``None`` if not extracted yet."""
        return json.loads(self.metadata_json) if self.metadata_json else None

    def __repr__(self):
        return f"WorkflowVersion<{self.id}>"
