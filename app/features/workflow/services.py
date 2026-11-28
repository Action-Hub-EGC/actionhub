import json
import logging
import os
import shutil
import zipfile
from datetime import datetime
from io import BytesIO

from splent_framework.services.BaseService import BaseService

from app.features.dataset.models import Author, DatasetVersion, DSMetaData, PublicationType
from app.features.dataset.services import calculate_checksum_and_size
from app.features.hubfile.models import Hubfile
from app.features.hubfile.services import HubfileService
from app.features.workflow.lifecycle import transition
from app.features.workflow.metadata import MetadataError, WorkflowMetadataExtractor
from app.features.workflow.models import ValidationStatus, WorkflowDataset, WorkflowVersion
from app.features.workflow.package import PackageIssue, PackageValidator
from app.features.workflow.repositories import WorkflowDatasetRepository, WorkflowVersionRepository
from app.features.workflow.security import L4SecurityEvaluator, SecurityEvaluationError
from app.features.workflow.validation import L1Validator, L2Validator

logger = logging.getLogger(__name__)


class WorkflowDatasetService(BaseService):
    def __init__(self):
        super().__init__(WorkflowDatasetRepository())
        self.versions = WorkflowVersionRepository()

    def list_recent(self):
        return self.repository.list_recent()

    def get_or_404(self, dataset_id: int):
        return self.repository.get_or_404(dataset_id)

    def versions_for(self, dataset_id: int):
        return self.versions.list_for_dataset(dataset_id)

    def validate_l1_text(self, text: str):
        return L1Validator().validate_text(text)

    def validate_l1_version(self, version):
        """Run blocking validation (L1 + L2) on a version.

        Delegates to ``validate_l2_version`` so no public entry point can mark
        a workflow as ``validated`` without passing both L1 and L2.
        """
        return self.validate_l2_version(version)

    def validate_l2_text(self, text: str):
        return L2Validator().validate_text(text)

    def validate_l2_version(self, version):
        """Run L1 + L2 on a version, update status and compute L4 security grade.

        L1 and L2 are blocking: a failure in either layer sets
        ``validation_status='failed'`` and blocks transition to ``validated``.
        L4 is non-blocking: once L1 + L2 pass, ``security_score`` and ``grade``
        are stored regardless of how low the grade is.
        A published workflow cannot be validated again (``InvalidTransition``, #19).
        """
        workflow = version.workflow_dataset
        result = L2Validator().validate_text(version.workflow_yaml)
        transition(workflow, ValidationStatus.VALIDATED if result.valid else ValidationStatus.FAILED)
        if result.valid:
            security = L4SecurityEvaluator().evaluate_text(version.workflow_yaml)
            workflow.security_score = security.score
            workflow.grade = security.grade
        else:
            workflow.security_score = None
            workflow.grade = None
        self.repository.session.commit()
        return result

    def upload_package(self, file_storage, current_user) -> tuple[WorkflowDataset | None, list[PackageIssue]]:
        """Validate and persist a workflow ``.zip`` package.

        Nothing is written to the database until the whole package passes
        structure, manifest and YAML checks. The workflow is stored as an
        unpublished draft (no DOI) with ``validation_status='validated'``,
        and its version carries the extracted workflow metadata (#17).
        """
        data = file_storage.read() if file_storage else b""
        result = PackageValidator().validate_zip(data)
        if not result.valid:
            return None, result.issues

        try:
            dataset = self.store_package(result, current_user)
        except Exception as exc:
            logger.exception("Could not persist workflow package: %s", exc)
            return None, [PackageIssue("No se pudo guardar el paquete. Revisa los datos e inténtalo de nuevo.")]
        return dataset, []

    def store_package(self, result, owner, **fields) -> WorkflowDataset:
        """Persist a package that already passed ``PackageValidator`` and commit.

        Creates the metadata, the workflow (``validation_status='validated'``
        unless ``fields`` says otherwise), its version 1, the ``WorkflowVersion``
        with ``metadata_json`` and one ``Hubfile`` per package file, written
        under ``HubfileService.version_directory``. ``fields`` sets extra
        ``WorkflowDataset`` columns, e.g. ``grade`` and ``security_score`` from
        the seeders. On any error the session is rolled back, the written
        files are removed and the exception is raised again.
        """
        manifest = result.manifest
        session = self.repository.session
        destination = None
        try:
            metadata = DSMetaData(
                title=manifest["name"],
                description=manifest["description"],
                publication_type=PublicationType.NONE,
                tags=", ".join(manifest.get("tags", [])) or None,
            )
            session.add(metadata)
            session.flush()

            for author in manifest.get("authors", []):
                session.add(
                    Author(
                        name=author["name"],
                        affiliation=author.get("affiliation"),
                        ds_meta_data_id=metadata.id,
                    )
                )

                        security = L4SecurityEvaluator().evaluate_text(result.workflow_yaml)
            manifest_json = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
            columns = {
                "validation_status": ValidationStatus.VALIDATED,
                "security_score": security.score,
                "grade": security.grade,
                "package_format": "zip",
                **fields,
            }
            dataset = WorkflowDataset(
                user_id=owner.id,
                ds_meta_data_id=metadata.id,
                manifest_json=manifest_json,
                **columns,
            )
            session.add(dataset)
            session.flush()

            dataset_version = DatasetVersion(
                dataset_id=dataset.id,
                number=1,
                created_at=dataset.created_at or datetime.utcnow(),
            )
            session.add(dataset_version)
            session.flush()

            version = WorkflowVersion(
                workflow_dataset_id=dataset.id,
                dataset_version_id=dataset_version.id,
                manifest_json=manifest_json,
                workflow_yaml=result.workflow_yaml,
                metadata_json=self.metadata_json_for(result.workflow_yaml),
                created_at=datetime.utcnow(),
            )
            session.add(version)
            session.flush()

            # #37: files live under their version, never in a shared folder.
            destination = HubfileService().version_directory(dataset, dataset_version)
            os.makedirs(destination, exist_ok=True)

            for name, content in result.files.items():
                target = os.path.join(destination, name)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, "wb") as handle:
                    handle.write(content)
                checksum, size = calculate_checksum_and_size(target)
                session.add(
                    Hubfile(
                        name=name,
                        checksum=checksum,
                        size=size,
                        workflow_version_id=version.id,
                    )
                )

            session.commit()
            return dataset
        except Exception:
            session.rollback()
            if destination:
                shutil.rmtree(destination, ignore_errors=True)
            raise

    def downloadable_version(self, workflow: WorkflowDataset, dataset_version=None) -> WorkflowVersion | None:
        """Workflow version that a download serves.

        ``dataset_version`` defaults to the latest published version, then to
        the latest draft, like the dataset download. Versions created before
        #36 have no ``DatasetVersion``; they fall back to the latest
        ``WorkflowVersion``.
        """
        dataset_version = (
            dataset_version or workflow.latest_published_dataset_version() or workflow.latest_dataset_version()
        )
        if dataset_version is not None and dataset_version.workflow_version is not None:
            return dataset_version.workflow_version
        return workflow.latest_version()

    def build_package_archive(self, workflow: WorkflowDataset, version=None) -> tuple[bytes, str] | None:
        """Zip one version of the package and return ``(zip_bytes, filename)``.

        The archive holds exactly the files uploaded for that version, at the
        root and under their original names (``fixtures/x.txt`` included), so
        it is a package that ``PackageValidator`` accepts again. Entries come
        from the version's ``Hubfile`` rows, never from walking the folder,
        and their paths from ``HubfileService`` (#37). Returns ``None`` when
        the workflow has no version with files. A file missing on disk raises
        ``FileNotFoundError``.
        """
        workflow_version = self.downloadable_version(workflow, version)
        if workflow_version is None or not workflow_version.files:
            return None

        hubfiles = HubfileService()
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for hubfile in sorted(workflow_version.files, key=lambda item: item.name):
                archive.write(hubfiles.get_path_by_hubfile(hubfile), arcname=hubfile.name)
        return buffer.getvalue(), self.package_filename(workflow, workflow_version)

    @staticmethod
    def package_filename(workflow: WorkflowDataset, workflow_version: WorkflowVersion) -> str:
        """``<name>-<version>.zip`` from the manifest, or ``workflow_<id>.zip``."""
        try:
            manifest = json.loads(workflow_version.manifest_json or "{}")
        except ValueError:
            manifest = {}
        name = manifest.get("name") if isinstance(manifest, dict) else None
        if not name:
            return f"workflow_{workflow.id}.zip"
        version = manifest.get("version")
        return f"{name}-{version}.zip" if version else f"{name}.zip"

    def extract_metadata(self, text: str):
        return WorkflowMetadataExtractor().extract_text(text)

    def metadata_json_for(self, text: str) -> str | None:
        """Metadata (#17) of a workflow that already passed validation, as JSON.

        This is the single place that computes ``WorkflowVersion.metadata_json``.
        It must only be called on the path that has run every blocking
        validation layer (today ``upload_package``). A document that is not a
        workflow mapping yields ``None`` instead of an error.
        """
        try:
            return self.extract_metadata(text).to_json()
        except MetadataError:
            logger.warning("Workflow metadata could not be extracted: not a YAML mapping")
            return None

    def evaluate_security(self, text: str):
        """Evaluate L4 security rules and return a ``SecurityReport``."""
        return L4SecurityEvaluator().evaluate_text(text)

    def security_report_for(self, workflow: WorkflowDataset):
        """Compute the L4 report for the current version of ``workflow``, or ``None``."""
        latest = workflow.latest_version()
        if latest is None or not latest.workflow_yaml:
            return None
        try:
            return self.evaluate_security(latest.workflow_yaml)
        except SecurityEvaluationError:
            return None
