from splent_framework.repositories.BaseRepository import BaseRepository

from app.features.workflow.models import WorkflowDataset, WorkflowVersion


class WorkflowDatasetRepository(BaseRepository):
    def __init__(self):
        super().__init__(WorkflowDataset)

    def list_recent(self):
        return self.model.query.order_by(self.model.created_at.desc()).all()


class WorkflowVersionRepository(BaseRepository):
    def __init__(self):
        super().__init__(WorkflowVersion)

    def list_for_dataset(self, dataset_id: int):
        return self.model.query.filter_by(workflow_dataset_id=dataset_id).order_by(self.model.created_at.desc()).all()
