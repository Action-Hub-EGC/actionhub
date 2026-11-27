"""Aggregation tests for the owner metrics (#62).

The fixtures build two owners with very different activity so that a missing
``DataSet.user_id`` filter or an accidental join through the record's
``user_id`` shows up as a wrong number, not as a subtle ordering difference.
"""

from datetime import datetime, timezone

import pytest

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import DataSet, DSDownloadRecord, DSMetaData, DSViewRecord, PublicationType
from app.features.featuremodel.models import FeatureModel
from app.features.hubfile.models import Hubfile, HubfileDownloadRecord, HubfileViewRecord
from app.features.metrics.services import MetricsService
from app.features.profile.services import UserProfileService
from app.features.workflow.models import WorkflowDataset, WorkflowVersion

pytestmark = pytest.mark.service

BASE_TIME = datetime(2024, 1, 1, 12, 0, 0)


def make_user(email):
    return UserRepository().create(email=email, password="secret")


def make_dataset(owner_id, title, *, doi=None, created_at=BASE_TIME):
    meta = DSMetaData(
        title=title,
        description=f"Description for {title}",
        publication_type=PublicationType.NONE,
        dataset_doi=doi,
    )
    db.session.add(meta)
    db.session.flush()
    dataset = DataSet(user_id=owner_id, ds_meta_data_id=meta.id, created_at=created_at)
    db.session.add(dataset)
    db.session.commit()
    return dataset


def make_version(dataset_id, file_sizes):
    version = FeatureModel(data_set_id=dataset_id)
    db.session.add(version)
    db.session.flush()
    files = [
        Hubfile(name=f"file-{index}.yml", checksum=f"sum-{index}", size=size, feature_model_id=version.id)
        for index, size in enumerate(file_sizes)
    ]
    db.session.add_all(files)
    db.session.commit()
    return version, files


def make_workflow(owner_id, title, *, doi=None, created_at=BASE_TIME):
    meta = DSMetaData(
        title=title,
        description=f"Description for {title}",
        publication_type=PublicationType.NONE,
        dataset_doi=doi,
    )
    db.session.add(meta)
    db.session.flush()
    workflow = WorkflowDataset(user_id=owner_id, ds_meta_data_id=meta.id, manifest_json="{}", created_at=created_at)
    db.session.add(workflow)
    db.session.commit()
    return workflow


def make_workflow_version(workflow_id, file_sizes):
    version = WorkflowVersion(
        workflow_dataset_id=workflow_id,
        manifest_json="{}",
        workflow_yaml="name: demo\non: push\njobs: {}\n",
        created_at=BASE_TIME,
    )
    db.session.add(version)
    db.session.flush()
    files = [
        Hubfile(name=f"wf-{index}.yml", checksum=f"wf-sum-{index}", size=size, workflow_version_id=version.id)
        for index, size in enumerate(file_sizes)
    ]
    db.session.add_all(files)
    db.session.commit()
    return version, files


def add_dataset_view(dataset_id, cookie, when, user_id=None):
    db.session.add(DSViewRecord(dataset_id=dataset_id, view_cookie=cookie, view_date=when, user_id=user_id))


def add_dataset_download(dataset_id, cookie, when, user_id=None):
    db.session.add(DSDownloadRecord(dataset_id=dataset_id, download_cookie=cookie, download_date=when, user_id=user_id))


def add_file_view(file_id, cookie, when, user_id=None):
    db.session.add(HubfileViewRecord(file_id=file_id, view_cookie=cookie, view_date=when, user_id=user_id))


def add_file_download(file_id, cookie, when, user_id=None):
    db.session.add(HubfileDownloadRecord(file_id=file_id, download_cookie=cookie, download_date=when, user_id=user_id))


def test_owner_summary_counts_catalog_and_activity(test_app, test_client):
    with test_app.app_context():
        owner = make_user("metrics-owner@example.com")
        stranger = make_user("metrics-stranger@example.com")

        published = make_dataset(owner.id, "published", doi="10.5281/zenodo.1")
        draft = make_dataset(owner.id, "draft")
        foreign = make_dataset(stranger.id, "foreign", doi="10.5281/zenodo.2")

        _, published_files = make_version(published.id, [100, 200])
        _, draft_files = make_version(draft.id, [50])
        _, foreign_files = make_version(foreign.id, [999])

        # Views and downloads: the actor is the stranger, not the owner.
        add_dataset_view(published.id, "cookie-a", datetime(2024, 1, 5, 10), user_id=stranger.id)
        add_dataset_view(published.id, "cookie-b", datetime(2024, 1, 5, 11))
        add_dataset_view(published.id, "cookie-a", datetime(2024, 1, 5, 12))
        add_dataset_view(draft.id, "cookie-a", datetime(2024, 1, 6, 9))
        add_dataset_view(foreign.id, "cookie-a", datetime(2024, 1, 7, 9))

        add_dataset_download(published.id, "cookie-a", datetime(2024, 1, 5, 13), user_id=stranger.id)
        add_dataset_download(published.id, "cookie-b", datetime(2024, 1, 5, 14))
        add_dataset_download(draft.id, "cookie-a", datetime(2024, 1, 6, 8))
        add_dataset_download(foreign.id, "cookie-a", datetime(2024, 1, 7, 9))

        add_file_view(published_files[0].id, "cookie-a", datetime(2024, 1, 4, 10))
        add_file_view(published_files[0].id, "cookie-b", datetime(2024, 1, 4, 11))
        add_file_view(published_files[1].id, "cookie-a", datetime(2024, 1, 4, 12))
        add_file_view(published_files[1].id, "cookie-c", datetime(2024, 1, 4, 13))
        add_file_view(draft_files[0].id, "cookie-a", datetime(2024, 1, 4, 14))
        add_file_view(foreign_files[0].id, "cookie-a", datetime(2024, 1, 7, 9))

        add_file_download(published_files[0].id, "cookie-a", datetime(2024, 1, 3, 10))
        add_file_download(published_files[1].id, "cookie-b", datetime(2024, 1, 3, 11))
        add_file_download(published_files[1].id, "cookie-c", datetime(2024, 1, 3, 12))
        add_file_download(draft_files[0].id, "cookie-a", datetime(2024, 1, 3, 13))
        add_file_download(foreign_files[0].id, "cookie-a", datetime(2024, 1, 7, 9))

        # Records without a live resource must not be counted: inner joins exclude them.
        add_dataset_view(None, "cookie-null", datetime(2024, 1, 8, 9))
        add_dataset_download(None, "cookie-null", datetime(2024, 1, 8, 9))

        db.session.commit()

        metrics = MetricsService().owner_summary(owner.id)

        assert metrics["workflows_total"] == 2
        assert metrics["published_total"] == 1
        assert metrics["draft_total"] == 1
        assert metrics["versions_total"] == 2
        assert metrics["files_total"] == 3
        assert metrics["size_total_bytes"] == 350
        assert metrics["workflow_views"] == 4
        assert metrics["workflow_downloads"] == 3
        assert metrics["file_views"] == 5
        assert metrics["file_downloads"] == 4
        assert metrics["unique_visitors"] == 2
        assert metrics["download_rate"] == pytest.approx(0.75)
        assert metrics["last_activity_at"] == datetime(2024, 1, 6, 9, tzinfo=timezone.utc)


def test_workflow_metrics_are_grouped_and_ordered_by_downloads(test_app, test_client):
    with test_app.app_context():
        owner = make_user("metrics-grouped@example.com")
        stranger = make_user("metrics-grouped-stranger@example.com")

        popular = make_dataset(owner.id, "popular", doi="10.5281/zenodo.3")
        quiet = make_dataset(owner.id, "quiet")
        foreign = make_dataset(stranger.id, "foreign", doi="10.5281/zenodo.4")

        make_version(popular.id, [100, 200, 300])
        make_version(quiet.id, [50])
        make_version(foreign.id, [999])

        add_dataset_view(popular.id, "cookie-a", datetime(2024, 2, 1, 9))
        add_dataset_view(popular.id, "cookie-b", datetime(2024, 2, 1, 10))
        add_dataset_view(quiet.id, "cookie-a", datetime(2024, 2, 2, 9))
        add_dataset_view(foreign.id, "cookie-a", datetime(2024, 2, 3, 9))

        add_dataset_download(popular.id, "cookie-a", datetime(2024, 2, 1, 11))
        add_dataset_download(popular.id, "cookie-b", datetime(2024, 2, 1, 12))
        add_dataset_download(quiet.id, "cookie-a", datetime(2024, 2, 2, 10))
        add_dataset_download(foreign.id, "cookie-a", datetime(2024, 2, 3, 10))

        db.session.commit()

        rows = MetricsService().workflows_for_owner(owner.id)

        assert [row["title"] for row in rows] == ["popular", "quiet"]
        assert rows[0]["published"] is True
        assert rows[0]["versions_total"] == 1
        assert rows[0]["files_total"] == 3
        assert rows[0]["workflow_views"] == 2
        assert rows[0]["workflow_downloads"] == 2
        assert rows[1]["published"] is False
        assert rows[1]["versions_total"] == 1
        assert rows[1]["files_total"] == 1
        assert rows[1]["workflow_views"] == 1
        assert rows[1]["workflow_downloads"] == 1


def test_download_rate_is_none_without_views(test_app, test_client):
    with test_app.app_context():
        owner = make_user("metrics-norate@example.com")
        dataset = make_dataset(owner.id, "downloads-only")
        add_dataset_download(dataset.id, "cookie-a", datetime(2024, 3, 1, 9))
        db.session.commit()

        metrics = MetricsService().owner_summary(owner.id)

        assert metrics["workflow_downloads"] == 1
        assert metrics["workflow_views"] == 0
        assert metrics["download_rate"] is None


def test_summary_for_user_keeps_its_contract_and_adds_metrics(test_app, test_client):
    with test_app.app_context():
        owner = make_user("metrics-summary@example.com")
        make_dataset(owner.id, "one", doi="10.5281/zenodo.5")
        make_dataset(owner.id, "two")

        summary = UserProfileService().summary_for_user(owner.id, page=1)

        assert len(summary["datasets"]) == 2
        assert summary["pagination"].pages == 1
        assert summary["total_datasets"] == 2
        assert summary["metrics"]["workflows_total"] == 2
        assert summary["metrics"]["published_total"] == 1
        assert summary["metrics"]["draft_total"] == 1


def test_owner_summary_counts_workflow_versions_and_files(test_app, test_client):
    with test_app.app_context():
        owner = make_user("metrics-workflow@example.com")
        stranger = make_user("metrics-workflow-stranger@example.com")

        workflow = make_workflow(owner.id, "ci", doi="10.5281/zenodo.10")
        _, files = make_workflow_version(workflow.id, [120])
        foreign = make_workflow(stranger.id, "foreign")
        _, foreign_files = make_workflow_version(foreign.id, [999])

        add_file_view(files[0].id, "cookie-a", datetime(2024, 4, 1, 9), user_id=stranger.id)
        add_file_download(files[0].id, "cookie-a", datetime(2024, 4, 2, 9))
        add_file_view(foreign_files[0].id, "cookie-a", datetime(2024, 5, 1, 9))
        add_file_download(foreign_files[0].id, "cookie-a", datetime(2024, 5, 1, 9))
        db.session.commit()

        metrics = MetricsService().owner_summary(owner.id)

        assert metrics["workflows_total"] == 1
        assert metrics["versions_total"] == 1
        assert metrics["files_total"] == 1
        assert metrics["size_total_bytes"] == 120
        assert metrics["file_views"] == 1
        assert metrics["file_downloads"] == 1
        assert metrics["last_activity_at"] == datetime(2024, 4, 2, 9, tzinfo=timezone.utc)

        [row] = MetricsService().workflows_for_owner(owner.id)
        assert row["title"] == "ci"
        assert row["versions_total"] == 1
        assert row["files_total"] == 1
        assert row["file_views"] == 1
        assert row["file_downloads"] == 1


def test_owner_summary_adds_uvl_and_workflow_without_double_counting(test_app, test_client):
    with test_app.app_context():
        owner = make_user("metrics-mixed@example.com")

        uvl = make_dataset(owner.id, "uvl", doi="10.5281/zenodo.11")
        _, uvl_files = make_version(uvl.id, [100, 200])
        workflow = make_workflow(owner.id, "workflow")
        _, workflow_files = make_workflow_version(workflow.id, [10, 20, 30])
        make_workflow_version(workflow.id, [5])

        add_file_view(uvl_files[0].id, "cookie-a", datetime(2024, 6, 1, 9))
        add_file_view(workflow_files[0].id, "cookie-a", datetime(2024, 6, 1, 10))
        add_file_view(workflow_files[1].id, "cookie-b", datetime(2024, 6, 1, 11))
        add_file_download(uvl_files[1].id, "cookie-a", datetime(2024, 6, 2, 9))
        add_file_download(workflow_files[2].id, "cookie-a", datetime(2024, 6, 3, 9))
        db.session.commit()

        metrics = MetricsService().owner_summary(owner.id)

        assert metrics["workflows_total"] == 2
        assert metrics["published_total"] == 1
        assert metrics["versions_total"] == 3
        assert metrics["files_total"] == 6
        assert metrics["size_total_bytes"] == 365
        assert metrics["file_views"] == 3
        assert metrics["file_downloads"] == 2
        assert metrics["last_activity_at"] == datetime(2024, 6, 3, 9, tzinfo=timezone.utc)

        rows = {row["title"]: row for row in MetricsService().workflows_for_owner(owner.id)}
        assert (rows["uvl"]["versions_total"], rows["uvl"]["files_total"]) == (1, 2)
        assert (rows["uvl"]["file_views"], rows["uvl"]["file_downloads"]) == (1, 1)
        assert (rows["workflow"]["versions_total"], rows["workflow"]["files_total"]) == (2, 4)
        assert (rows["workflow"]["file_views"], rows["workflow"]["file_downloads"]) == (2, 1)
