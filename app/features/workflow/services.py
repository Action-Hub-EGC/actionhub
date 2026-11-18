from splent_framework.services.BaseService import BaseService

from app.features.workflow.repositories import WorkflowDatasetRepository, WorkflowVersionRepository


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
