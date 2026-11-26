"""Workflow seeders with one example per grade, A to F (#21)."""

import os

import pytest

from app.features.auth.seeders import AuthSeeder
from app.features.dataset.seeders import DataSetSeeder
from app.features.hubfile.services import HubfileService
from app.features.metrics.seeders import MetricsSeeder
from app.features.workflow.models import ValidationStatus, WorkflowDataset
from app.features.workflow.package import PackageValidator
from app.features.workflow.seeders import SEED_WORKFLOWS, WorkflowSeeder, package_bytes
from app.features.workflow.services import WorkflowDatasetService

pytestmark = pytest.mark.service


@pytest.mark.parametrize("seed", SEED_WORKFLOWS, ids=lambda seed: seed.slug)
def test_every_seed_example_is_a_valid_package(seed):
    result = PackageValidator().validate_zip(package_bytes(seed.slug))

    assert result.valid is True, result.issues
    assert result.manifest["name"] == seed.slug


def test_seed_examples_cover_grades_a_to_f():
    assert sorted(seed.grade for seed in SEED_WORKFLOWS) == list("ABCDEF")
    scores = [seed.security_score for seed in sorted(SEED_WORKFLOWS, key=lambda seed: seed.grade)]
    assert scores == sorted(scores, reverse=True)


def test_workflow_seeder_runs_after_users_and_datasets_and_before_metrics():
    assert AuthSeeder.priority < DataSetSeeder.priority < WorkflowSeeder.priority < MetricsSeeder.priority


def test_workflow_seeder_creates_six_graded_workflows(test_app, clean_database, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    with test_app.app_context():
        AuthSeeder().run()
        WorkflowSeeder().run()

        workflows = WorkflowDataset.query.order_by(WorkflowDataset.grade).all()
        assert [workflow.grade for workflow in workflows] == list("ABCDEF")

        hubfiles = HubfileService()
        service = WorkflowDatasetService()
        for workflow, seed in zip(workflows, sorted(SEED_WORKFLOWS, key=lambda seed: seed.grade)):
            assert workflow.ds_meta_data.title == seed.slug
            assert workflow.security_score == seed.security_score
            assert workflow.package_format == "zip"

            dataset_version = workflow.latest_dataset_version()
            assert dataset_version.number == 1
            version = dataset_version.workflow_version
            assert version is not None
            assert version.workflow_metadata["triggers"]
            assert version.files
            for hubfile in version.files:
                path = hubfiles.get_path_by_hubfile(hubfile)
                assert path.startswith(hubfiles.version_directory(workflow, dataset_version))
                assert os.path.getsize(path) == hubfile.size

            if seed.published:
                assert workflow.validation_status == ValidationStatus.PUBLISHED
                assert workflow.ds_meta_data.dataset_doi == dataset_version.doi
                assert dataset_version.doi.startswith("10.1234/workflow")
                assert dataset_version.published_at is not None
            else:
                assert workflow.validation_status == ValidationStatus.VALIDATED
                assert dataset_version.doi is None

            data, _filename = service.build_package_archive(workflow)
            assert PackageValidator().validate_zip(data).valid is True

        assert {workflow.validation_status for workflow in workflows} == {
            ValidationStatus.PUBLISHED,
            ValidationStatus.VALIDATED,
        }


def test_workflow_seeder_does_not_duplicate_on_a_second_run(test_app, clean_database, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    with test_app.app_context():
        AuthSeeder().run()
        WorkflowSeeder().run()
        WorkflowSeeder().run()

        assert WorkflowDataset.query.count() == len(SEED_WORKFLOWS)


def test_workflow_seeder_requires_the_users(test_app, clean_database, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))
    with test_app.app_context():
        with pytest.raises(Exception, match="seed users first"):
            WorkflowSeeder().run()
