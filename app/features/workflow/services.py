from splent_framework.services.BaseService import BaseService

from app.features.workflow.models import ValidationStatus
from app.features.workflow.repositories import WorkflowDatasetRepository, WorkflowVersionRepository
from app.features.workflow.validation import L1Validator


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
