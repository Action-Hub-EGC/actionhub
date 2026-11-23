"""Per-version file storage and the pre-#37 compatibility path (#37)."""

import os
import shutil
from datetime import datetime, timezone
from zipfile import ZipFile

import pytest

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import DataSet, DatasetVersion, DSMetaData, PublicationType
from app.features.dataset.services import DataSetService
from app.features.featuremodel.models import FeatureModel
from app.features.hubfile.models import Hubfile
from app.features.hubfile.services import HubfileService

pytestmark = pytest.mark.service


def _dataset(email="files@example.com", title="Versioned files"):
    owner = UserRepository().create(email=email, password="secret")
    meta = DSMetaData(
        title=title,
        description="Dataset used by the file storage tests",
        publication_type=PublicationType.NONE,
    )
    db.session.add(meta)
    db.session.flush()
    dataset = DataSet(user_id=owner.id, ds_meta_data_id=meta.id, created_at=datetime.now(timezone.utc))
    db.session.add(dataset)
    db.session.flush()
    return owner, dataset


def _version(dataset, number, doi=None):
    version = DatasetVersion(
        dataset_id=dataset.id,
        number=number,
        doi=doi,
        created_at=datetime.now(timezone.utc),
        published_at=datetime.now(timezone.utc) if doi else None,
    )
    db.session.add(version)
    db.session.flush()
    return version


def _hubfile(dataset, version, name, size=10):
    feature_model = FeatureModel(data_set_id=dataset.id, dataset_version_id=version.id if version else None)
    db.session.add(feature_model)
    db.session.flush()
    hubfile = Hubfile(name=name, checksum=f"checksum-{name}", size=size, feature_model_id=feature_model.id)
    db.session.add(hubfile)
    db.session.commit()
    return hubfile


def _write(directory, name, content=b"features\n    Root\n"):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    with open(path, "wb") as handle:
        handle.write(content)
    return path


def test_files_of_each_version_live_in_their_own_folder(test_app, clean_database, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))

    with test_app.app_context():
        _, dataset = _dataset()
        first = _version(dataset, 1, doi="10.5072/file.1")
        second = _version(dataset, 2, doi="10.5072/file.2")
        first_file = _hubfile(dataset, first, "first.uvl")
        second_file = _hubfile(dataset, second, "second.uvl")

        service = HubfileService()
        first_dir = service.version_directory(dataset, first)
        second_dir = service.version_directory(dataset, second)
        _write(first_dir, "first.uvl")
        _write(second_dir, "second.uvl")

        assert first_dir.endswith(os.path.join(f"dataset_{dataset.id}", "v1"))
        assert second_dir.endswith(os.path.join(f"dataset_{dataset.id}", "v2"))
        assert service.get_path_by_hubfile(first_file) == os.path.join(first_dir, "first.uvl")
        assert service.get_path_by_hubfile(second_file) == os.path.join(second_dir, "second.uvl")


def test_version_one_without_a_v1_folder_is_read_from_the_legacy_root(test_app, clean_database, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))

    with test_app.app_context():
        _, dataset = _dataset("legacy-one@example.com")
        version = _version(dataset, 1, doi="10.5072/legacy.1")
        hubfile = _hubfile(dataset, version, "legacy.uvl")

        service = HubfileService()
        legacy_dir = service.dataset_directory(dataset)
        _write(legacy_dir, "legacy.uvl")

        assert service.read_directory(dataset, version) == legacy_dir
        assert service.get_path_by_hubfile(hubfile) == os.path.join(legacy_dir, "legacy.uvl")


def test_unversioned_rows_keep_reading_from_the_legacy_root(test_app, clean_database, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))

    with test_app.app_context():
        _, dataset = _dataset("legacy-none@example.com")
        hubfile = _hubfile(dataset, None, "old.uvl")

        service = HubfileService()
        legacy_dir = service.dataset_directory(dataset)
        _write(legacy_dir, "old.uvl")

        assert service.get_path_by_hubfile(hubfile) == os.path.join(legacy_dir, "old.uvl")


def test_download_archive_contains_only_the_requested_version(test_app, clean_database, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))

    with test_app.app_context():
        _, dataset = _dataset("archive-version@example.com")
        first = _version(dataset, 1, doi="10.5072/archive.1")
        second = _version(dataset, 2, doi="10.5072/archive.2")
        _hubfile(dataset, first, "first.uvl")
        _hubfile(dataset, second, "second.uvl")

        service = HubfileService()
        first_path = _write(service.version_directory(dataset, first), "first.uvl")
        _write(service.version_directory(dataset, second), "second.uvl")

        tmp_dir, zip_name = DataSetService().build_download_archive(dataset, first)
        with ZipFile(os.path.join(tmp_dir, zip_name)) as archive:
            assert archive.namelist() == [f"dataset_{dataset.id}/first.uvl"]
        shutil.rmtree(tmp_dir, ignore_errors=True)

        tmp_dir, zip_name = DataSetService().build_download_archive(dataset, second)
        with ZipFile(os.path.join(tmp_dir, zip_name)) as archive:
            assert archive.namelist() == [f"dataset_{dataset.id}/second.uvl"]
        shutil.rmtree(tmp_dir, ignore_errors=True)

        # Publishing or downloading v2 never deletes what v1 still owns.
        assert os.path.exists(first_path)


def test_legacy_archive_skips_version_folders(test_app, clean_database, monkeypatch, tmp_path):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))

    with test_app.app_context():
        _, dataset = _dataset("archive-legacy@example.com")
        legacy_dir = HubfileService().dataset_directory(dataset)
        _write(legacy_dir, "legacy.uvl")
        _write(os.path.join(legacy_dir, "v2"), "newer.uvl")

        tmp_dir, zip_name = DataSetService().build_download_archive(dataset)
        with ZipFile(os.path.join(tmp_dir, zip_name)) as archive:
            assert archive.namelist() == [f"dataset_{dataset.id}/legacy.uvl"]
        shutil.rmtree(tmp_dir, ignore_errors=True)
