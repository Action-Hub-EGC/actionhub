"""L4 security rules, A-F grading and warning UI tests (#18)."""

import io

import pytest

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import DSMetaData, PublicationType
from app.features.workflow.models import ValidationStatus, WorkflowDataset, WorkflowVersion
from app.features.workflow.security import L4SecurityEvaluator, grade_for_score, has_security_warning
from app.features.workflow.services import WorkflowDatasetService
from app.features.workflow.tests.test_lifecycle import FakenodoRequests, signup
from app.features.workflow.tests.test_package import make_zip
from fakenodo.app import create_app as create_fakenodo
from fakenodo.store import DepositionStore

PINNED_CHECKOUT = "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"
PINNED_SETUP_PYTHON = "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065"

SECURE_WORKFLOW = f"""name: Secure CI
on: push
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: {PINNED_CHECKOUT}
      - run: pytest
"""

LOW_GRADE_WORKFLOW = """name: Risky PR workflow
on: pull_request_target
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - uses: actions/setup-python@v5
"""


# ── Pure rule and boundary tests ────────────────────────────────────────


@pytest.mark.unit
def test_secure_workflow_scores_100_grade_a_without_warning():
    report = L4SecurityEvaluator().evaluate_text(SECURE_WORKFLOW)

    assert report.score == 100
    assert report.grade == "A"
    assert report.findings == []
    assert report.has_warning is False
    assert report.warning_message is None


@pytest.mark.unit
def test_sec01_penalizes_unpinned_external_actions_with_cap_of_45():
    workflow = f"""name: Unpinned actions
on: push
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: ./local-action
      - uses: {PINNED_CHECKOUT}
      - uses: actions/checkout@v4
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
      - uses: actions/cache@v4
      - uses: docker://alpine:3.19
"""
    report = L4SecurityEvaluator().evaluate_text(workflow)

    sec01_findings = [finding for finding in report.findings if finding.rule_id == "SEC-01"]
    assert len(sec01_findings) == 4
    assert sum(finding.penalty for finding in sec01_findings) == 45
    assert report.score == 55
    assert report.grade == "E"
    assert report.has_warning is True


@pytest.mark.unit
def test_sec01_accepts_pinned_docker_digest_and_reusable_workflow_sha():
    workflow = """name: Pinned docker and reusable
on: push
permissions:
  contents: read
jobs:
  call-reusable:
    uses: org/repo/.github/workflows/ci.yml@11bd71901bbe5b1630ceea73d27597364c9af683
  container-step:
    runs-on: ubuntu-latest
    steps:
      - uses: docker://alpine@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
"""
    report = L4SecurityEvaluator().evaluate_text(workflow)

    assert report.score == 100
    assert report.grade == "A"
    assert report.findings == []


@pytest.mark.unit
def test_sec02_penalizes_missing_permissions_once_per_workflow():
    workflow = f"""name: Missing permissions
on: push
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: {PINNED_CHECKOUT}
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: {PINNED_SETUP_PYTHON}
"""
    report = L4SecurityEvaluator().evaluate_text(workflow)

    assert [finding.rule_id for finding in report.findings] == ["SEC-02"]
    assert report.findings[0].penalty == 10
    assert report.score == 90
    assert report.grade == "A"


@pytest.mark.unit
def test_sec02_passes_when_every_job_declares_permissions():
    workflow = f"""name: Job permissions
on: push
jobs:
  lint:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: {PINNED_CHECKOUT}
  test:
    runs-on: ubuntu-latest
    permissions: {{}}
    steps:
      - uses: {PINNED_SETUP_PYTHON}
"""
    report = L4SecurityEvaluator().evaluate_text(workflow)

    assert report.score == 100
    assert report.findings == []


@pytest.mark.unit
def test_sec03_penalizes_write_all_once_at_root_or_job_level():
    root_write_all = f"""name: Root write-all
on: push
permissions: write-all
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: {PINNED_CHECKOUT}
"""
    job_write_all = f"""name: Job write-all
on: push
permissions:
  contents: read
jobs:
  first:
    runs-on: ubuntu-latest
    permissions: write-all
    steps:
      - uses: {PINNED_CHECKOUT}
  second:
    runs-on: ubuntu-latest
    permissions: write-all
    steps:
      - uses: {PINNED_SETUP_PYTHON}
"""

    for yaml_text in (root_write_all, job_write_all):
        report = L4SecurityEvaluator().evaluate_text(yaml_text)
        assert [finding.rule_id for finding in report.findings] == ["SEC-03"]
        assert report.findings[0].penalty == 10
        assert report.score == 90
        assert report.grade == "A"


@pytest.mark.unit
def test_sec04_penalizes_each_pull_request_target_head_checkout():
    workflow = f"""name: PR target head checkout
on:
  pull_request_target:
    types: [opened, synchronize]
permissions:
  contents: read
jobs:
  first:
    runs-on: ubuntu-latest
    steps:
      - uses: {PINNED_CHECKOUT}
        with:
          ref: ${{{{ github.event.pull_request.head.sha }}}}
  second:
    runs-on: ubuntu-latest
    steps:
      - uses: {PINNED_CHECKOUT}
        with:
          ref: ${{{{ github.head_ref }}}}
"""
    report = L4SecurityEvaluator().evaluate_text(workflow)

    assert [finding.rule_id for finding in report.findings] == ["SEC-04", "SEC-04"]
    assert [finding.penalty for finding in report.findings] == [25, 25]
    assert report.score == 50
    assert report.grade == "E"
    assert report.has_warning is True


@pytest.mark.unit
def test_sec04_does_not_trigger_on_base_checkout_or_regular_pull_request():
    safe_base = f"""name: Safe PR target
on: pull_request_target
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: {PINNED_CHECKOUT}
"""
    safe_pr = f"""name: Regular PR
on: [push, pull_request]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: {PINNED_CHECKOUT}
        with:
          ref: ${{{{ github.event.pull_request.head.sha }}}}
"""

    assert L4SecurityEvaluator().evaluate_text(safe_base).score == 100
    assert L4SecurityEvaluator().evaluate_text(safe_pr).score == 100


@pytest.mark.unit
def test_score_never_drops_below_zero():
    workflow = """name: Worst case
on: pull_request_target
permissions: write-all
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - uses: actions/checkout@v3
        with:
          ref: ${{ github.head_ref }}
      - uses: actions/setup-python@v5
      - uses: actions/checkout@v2
        with:
          ref: refs/pull/${{ github.event.pull_request.number }}/head
"""
    report = L4SecurityEvaluator().evaluate_text(workflow)

    assert report.score == 0
    assert report.grade == "F"
    assert report.has_warning is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("score", "expected_grade", "expected_warning"),
    [
        (100, "A", False),
        (90, "A", False),
        (89, "B", False),
        (80, "B", False),
        (79, "C", False),
        (70, "C", False),
        (69, "D", True),
        (60, "D", True),
        (59, "E", True),
        (50, "E", True),
        (49, "F", True),
        (0, "F", True),
    ],
)
def test_grade_band_boundaries_and_warning_threshold(score, expected_grade, expected_warning):
    assert grade_for_score(score) == expected_grade
    assert has_security_warning(expected_grade) is expected_warning


# ── Service and UI integration tests ────────────────────────────────────


@pytest.mark.service
def test_validate_l2_version_stores_l4_grade_and_clears_on_failure(test_app, test_client):
    with test_app.app_context():
        owner = UserRepository().create(email="l4-service@example.com", password="secret")
        meta = DSMetaData(title="L4 check", description="L4 service test", publication_type=PublicationType.NONE)
        db.session.add(meta)
        db.session.flush()
        dataset = WorkflowDataset(user_id=owner.id, ds_meta_data_id=meta.id, validation_status=ValidationStatus.DRAFT)
        db.session.add(dataset)
        db.session.flush()
        version = WorkflowVersion(
            workflow_dataset_id=dataset.id,
            manifest_json="{}",
            workflow_yaml=LOW_GRADE_WORKFLOW,
        )
        db.session.add(version)
        db.session.commit()

        result = WorkflowDatasetService().validate_l2_version(version)

        # L4 is non-blocking: grade F still moves to validated.
        assert result.valid is True
        assert dataset.validation_status == ValidationStatus.VALIDATED
        assert dataset.security_score == 35
        assert dataset.grade == "F"
        assert dataset.has_security_warning() is True

        # Blocking L2 failure clears stored grade and marks failed.
        version.workflow_yaml = "name: broken\non: push\njobs: {}\n"
        db.session.commit()
        failed = WorkflowDatasetService().validate_l2_version(version)

        assert failed.valid is False
        assert dataset.validation_status == ValidationStatus.FAILED
        assert dataset.security_score is None
        assert dataset.grade is None


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def fakenodo(tmp_path, monkeypatch):
    app = create_fakenodo(DepositionStore(tmp_path / "fakenodo.sqlite3"))
    app.config["TESTING"] = True
    monkeypatch.setenv("ZENODO_API_URL", "http://fakenodo:8000/api/deposit/depositions")
    fake = FakenodoRequests(app.test_client())
    monkeypatch.setattr("app.features.zenodo.services.requests", fake)
    return fake


@pytest.mark.integration
def test_workflow_below_grade_c_publishes_and_shows_security_warning(test_client, uploads, fakenodo):
    signup(test_client, "l4-warning-route@example.com")

    upload = test_client.post(
        "/workflow/upload",
        data={"package": (io.BytesIO(make_zip(workflow=LOW_GRADE_WORKFLOW)), "workflow.zip")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload.status_code == 302
    dataset_id = int(upload.headers["Location"].rstrip("/").split("/")[-1])

    detail = test_client.get(f"/workflow/{dataset_id}")
    detail_html = detail.get_data(as_text=True)
    assert detail.status_code == 200
    assert "workflow-security-warning" in detail_html
    assert "Advertencia de seguridad" in detail_html
    assert "SEC-01" in detail_html
    assert "SEC-02" in detail_html
    assert "SEC-04" in detail_html

    publish = test_client.post(f"/workflow/{dataset_id}/publish", follow_redirects=True)
    publish_html = publish.get_data(as_text=True)
    assert publish.status_code == 200
    assert "10.5072/fakenodo." in publish_html
    assert "published" in publish_html
    assert "Advertencia de seguridad" in publish_html


@pytest.mark.integration
def test_secure_workflow_does_not_show_security_warning(test_client, uploads):
    signup(test_client, "l4-secure-route@example.com")

    upload = test_client.post(
        "/workflow/upload",
        data={"package": (io.BytesIO(make_zip(workflow=SECURE_WORKFLOW)), "workflow.zip")},
        content_type="multipart/form-data",
        follow_redirects=False,
    )
    assert upload.status_code == 302
    dataset_id = int(upload.headers["Location"].rstrip("/").split("/")[-1])

    detail = test_client.get(f"/workflow/{dataset_id}")
    detail_html = detail.get_data(as_text=True)
    assert detail.status_code == 200
    assert "workflow-security-warning" not in detail_html
    assert "Advertencia de seguridad" not in detail_html
    assert "100" in detail_html
