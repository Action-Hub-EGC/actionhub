import logging
import uuid
from io import BytesIO

from flask import abort, flash, jsonify, make_response, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required

from app.features.dataset.services import DSDownloadRecordService, DSViewRecordService
from app.features.metrics.services import DatasetCounterService
from app.features.workflow import workflow_bp
from app.features.workflow.forms import WorkflowPackageForm, WorkflowPublishForm
from app.features.workflow.lifecycle import InvalidTransition, PublicationError, WorkflowPublicationService
from app.features.workflow.services import WorkflowDatasetService

logger = logging.getLogger(__name__)

workflow_service = WorkflowDatasetService()
view_record_service = DSViewRecordService()
counter_service = DatasetCounterService()
download_record_service = DSDownloadRecordService()


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
    # Same view record and cookie as the dataset page, so both count alike (#67).
    view_cookie = view_record_service.create_cookie(dataset=workflow)
    response = make_response(
        render_template(
            "workflow/detail.html",
            workflow=workflow,
            versions=workflow_service.versions_for(dataset_id),
            workflow_metadata=workflow.workflow_metadata(),
            security_report=workflow_service.security_report_for(workflow),
            counts=counter_service.counts(dataset_id),
            publish_form=WorkflowPublishForm(),
        )
    )
    response.set_cookie("view_cookie", view_cookie, max_age=60 * 60 * 24 * 365 * 2)
    return response


@workflow_bp.route("/workflow/<int:dataset_id>/publish", methods=["POST"])
@login_required
def publish(dataset_id):
    workflow = workflow_service.get_or_404(dataset_id)
    if workflow.user_id != current_user.id:
        abort(403)
    form = WorkflowPublishForm()
    if not form.validate_on_submit():
        abort(400)
    try:
        doi = WorkflowPublicationService().publish(workflow)
    except (InvalidTransition, PublicationError) as exc:
        flash(str(exc), "danger")
    else:
        logger.info("Workflow %s published with DOI %s", dataset_id, doi)
        flash(f"Workflow publicado con DOI {doi}.", "success")
        if workflow.has_security_warning():
            flash(
                f"Advertencia de seguridad: este workflow se ha publicado con calificación {workflow.grade} "
                f"({workflow.security_score}/100).",
                "warning",
            )
    return redirect(url_for("workflow.detail", dataset_id=dataset_id))


@workflow_bp.route("/workflow/<int:dataset_id>/download")
def download(dataset_id):
    """Download the package of the latest published version, or the latest draft, as a ``.zip``."""
    workflow = workflow_service.get_or_404(dataset_id)
    try:
        archive = workflow_service.build_package_archive(workflow)
    except FileNotFoundError:
        logger.exception("Workflow %s has files missing on disk", dataset_id)
        abort(404)
    if archive is None:
        abort(404)
    data, filename = archive

    # Same cookie and download record as the dataset download, so both count alike (#67).
    cookie = request.cookies.get("download_cookie") or str(uuid.uuid4())
    response = make_response(
        send_file(BytesIO(data), mimetype="application/zip", as_attachment=True, download_name=filename)
    )
    if not request.cookies.get("download_cookie"):
        response.set_cookie("download_cookie", cookie, max_age=60 * 60 * 24 * 365 * 2)
    download_record_service.record_download(current_user, dataset_id, cookie)
    return response
