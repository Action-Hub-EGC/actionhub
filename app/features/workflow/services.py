import json
import logging
import os
import shutil
from datetime import datetime

from splent_framework.services.BaseService import BaseService

from app.features.dataset.models import Author, DSMetaData, PublicationType
from app.features.dataset.services import calculate_checksum_and_size
from app.features.hubfile.models import Hubfile
from app.features.workflow.models import ValidationStatus, WorkflowDataset, WorkflowVersion
from app.features.workflow.package import PackageIssue, PackageValidator
from app.features.workflow.repositories import WorkflowDatasetRepository, WorkflowVersionRepository
from app.features.workflow.validation import L1Validator

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
        """Run L1 on a version and update the parent workflow status.

        A failure sets ``validation_status='failed'``; only a clean result
        moves the workflow to ``validated``.
        """
        result = L1Validator().validate_text(version.workflow_yaml)
        workflow = version.workflow_dataset
        workflow.validation_status = ValidationStatus.VALIDATED if result.valid else ValidationStatus.FAILED
        self.repository.session.commit()
        return result

    def upload_package(self, file_storage, current_user) -> tuple[WorkflowDataset | None, list[PackageIssue]]:
        """Validate and persist a workflow ``.zip`` package.

        Nothing is written to the database until the whole package passes
        structure, manifest and YAML checks. The workflow is stored as an
        unpublished draft (no DOI) with ``validation_status='validated'``.
        """
        data = file_storage.read() if file_storage else b""
        result = PackageValidator().validate_zip(data)
        if not result.valid:
            return None, result.issues

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

            manifest_json = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
            dataset = WorkflowDataset(
                user_id=current_user.id,
                ds_meta_data_id=metadata.id,
                manifest_json=manifest_json,
                validation_status=ValidationStatus.VALIDATED,
                package_format="zip",
            )
            session.add(dataset)
            session.flush()

            version = WorkflowVersion(
                workflow_dataset_id=dataset.id,
                manifest_json=manifest_json,
                workflow_yaml=result.workflow_yaml,
                created_at=datetime.utcnow(),
            )
            session.add(version)
            session.flush()

            working_dir = os.getenv("WORKING_DIR", "")
            destination = os.path.join(
                working_dir,
                "uploads",
                f"user_{current_user.id}",
                f"dataset_{dataset.id}",
            )
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
            return dataset, []
        except Exception as exc:
            session.rollback()
            if destination:
                shutil.rmtree(destination, ignore_errors=True)
            logger.exception("Could not persist workflow package: %s", exc)
            return None, [PackageIssue(f"No se pudo guardar el paquete: {exc}")]
