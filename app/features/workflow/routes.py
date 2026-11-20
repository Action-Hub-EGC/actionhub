import logging

from flask import jsonify, render_template
from flask_login import login_required

from app.features.workflow import workflow_bp
from app.features.workflow.forms import WorkflowDatasetForm
from app.features.workflow.services import WorkflowDatasetService

logger = logging.getLogger(__name__)

workflow_service = WorkflowDatasetService()


@workflow_bp.route("/workflow")
def index():
    logger.info("Access workflow index")
    return render_template("workflow/index.html", workflows=workflow_service.list_recent())


@workflow_bp.route("/workflow/health")
def health():
    return jsonify({"status": "ok", "feature": "workflow"})


@workflow_bp.route("/workflow/upload", methods=["GET"])
@login_required
def upload():
    return render_template("workflow/upload.html", form=WorkflowDatasetForm())


@workflow_bp.route("/workflow/<int:dataset_id>")
def detail(dataset_id):
    workflow = workflow_service.get_or_404(dataset_id)
    versions = workflow_service.versions_for(dataset_id)
    return render_template(
        "workflow/detail.html",
        workflow=workflow,
        versions=versions,
        workflow_metadata=versions[0].workflow_metadata if versions else None,
    )
