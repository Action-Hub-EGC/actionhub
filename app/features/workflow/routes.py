import logging

from flask import jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.features.workflow import workflow_bp
from app.features.workflow.forms import WorkflowPackageForm
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


@workflow_bp.route("/workflow/upload", methods=["GET", "POST"])
@login_required
def upload():
    form = WorkflowPackageForm()
    issues = []
    if form.validate_on_submit():
        dataset, issues = workflow_service.upload_package(form.package.data, current_user)
        if dataset:
            logger.info("Workflow package uploaded as dataset %s", dataset.id)
            return redirect(url_for("workflow.detail", dataset_id=dataset.id))
    return render_template("workflow/upload.html", form=form, issues=issues)


@workflow_bp.route("/workflow/<int:dataset_id>")
def detail(dataset_id):
    workflow = workflow_service.get_or_404(dataset_id)
    return render_template(
        "workflow/detail.html",
        workflow=workflow,
        versions=workflow_service.versions_for(dataset_id),
        workflow_metadata=workflow.workflow_metadata(),
    )
