"""Example workflows for ``rosemary db:seed`` (#21).

Each folder under ``seed_examples/`` is a workflow package with the same
layout users upload. The seeder zips it, runs it through
``PackageValidator`` and stores it with ``WorkflowDatasetService.store_package``,
the same path as an upload, so every seed has version 1, a ``WorkflowVersion``
with ``metadata_json`` and real ``Hubfile`` rows under the version folder.

L4 grading (#18) does not exist yet, so the grade and score are set here and
each example's content is written to deserve its grade: A pins actions by SHA
and grants minimal permissions; F uses ``pull_request_target`` with the PR
code, ``write-all`` and echoes secrets.
"""

import io
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from splent_framework.seeders.BaseSeeder import BaseSeeder

from app.features.auth.models import User
from app.features.dataset.models import DSMetaData
from app.features.workflow.lifecycle import transition
from app.features.workflow.models import ValidationStatus, WorkflowDataset
from app.features.workflow.package import PackageValidator
from app.features.workflow.services import WorkflowDatasetService

SEED_EXAMPLES_DIR = Path(__file__).resolve().parent / "seed_examples"


@dataclass(frozen=True)
class SeedWorkflow:
    slug: str
    grade: str
    security_score: int
    owner_email: str
    published: bool


SEED_WORKFLOWS = (
    SeedWorkflow("secure-node-ci", "A", 96, "user1@example.com", True),
    SeedWorkflow("python-test-matrix", "B", 84, "user2@example.com", True),
    SeedWorkflow("docker-image-publish", "C", 71, "user1@example.com", True),
    SeedWorkflow("nightly-dependency-update", "D", 55, "user2@example.com", False),
    SeedWorkflow("issue-label-bot", "E", 38, "user1@example.com", False),
    SeedWorkflow("pr-preview-deploy", "F", 9, "user2@example.com", True),
)


def package_bytes(slug: str) -> bytes:
    """Zip ``seed_examples/<slug>/`` with the files at the archive root."""
    source = SEED_EXAMPLES_DIR / slug
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=path.relative_to(source).as_posix())
    return buffer.getvalue()


class WorkflowSeeder(BaseSeeder):

    # After the users (1) and the UVL datasets (2), so the UVL seeds keep
    # ids 1-4, and before metrics (4) so the workflows also get activity.
    priority = 3

    def run(self):
        service = WorkflowDatasetService()
        validator = PackageValidator()

        for number, seed in enumerate(SEED_WORKFLOWS, start=1):
            if self._already_seeded(seed.slug):
                continue

            owner = User.query.filter_by(email=seed.owner_email).first()
            if owner is None:
                raise Exception("Users not found. Please seed users first.")

            result = validator.validate_zip(package_bytes(seed.slug))
            if not result.valid:
                details = "; ".join(issue.message for issue in result.issues)
                raise Exception(f"Seed workflow '{seed.slug}' is not a valid package: {details}")

            workflow = service.store_package(
                result,
                owner,
                grade=seed.grade,
                security_score=seed.security_score,
            )
            if seed.published:
                self._publish(workflow, f"10.1234/workflow{number}")

    @staticmethod
    def _already_seeded(slug: str) -> bool:
        return WorkflowDataset.query.join(DSMetaData).filter(DSMetaData.title == slug).first() is not None

    def _publish(self, workflow: WorkflowDataset, doi: str) -> None:
        """Mark a seeded workflow as published with a fake DOI, without calling Zenodo."""
        version = workflow.latest_dataset_version()
        version.doi = doi
        version.published_at = datetime.now(timezone.utc).replace(tzinfo=None)
        workflow.ds_meta_data.dataset_doi = doi
        transition(workflow, ValidationStatus.PUBLISHED)
        self.db.session.commit()
