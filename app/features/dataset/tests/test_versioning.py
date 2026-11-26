"""Dataset versions and concept DOI (#36)."""

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import (
    BaseDataset,
    DataSet,
    DatasetVersion,
    PublicationType,
)
from app.features.dataset.repositories import DSMetaDataRepository
from app.features.dataset.services import DataSetService
from app.features.featuremodel.models import FeatureModel
from app.features.hubfile.models import Hubfile
from app.features.profile.models import UserProfile

pytestmark = pytest.mark.repository


def _user(email="versions@example.com"):
    user = UserRepository().create(email=email, password="secret")
    db.session.add(
        UserProfile(
            user_id=user.id,
            name="Olivia",
            surname="Owner",
            affiliation="University",
        )
    )
    db.session.commit()
    return user


def _form():
    feature_model_form = SimpleNamespace(
        uvl_filename=SimpleNamespace(data="model.uvl"),
        get_fmmetadata=lambda: {
            "uvl_filename": "model.uvl",
            "title": "Model",
            "description": "A feature model",
            "publication_type": PublicationType.NONE.name,
            "publication_doi": None,
            "tags": None,
            "uvl_version": None,
        },
        get_authors=lambda: [],
    )
    return SimpleNamespace(
        get_dsmetadata=lambda: {
            "title": "Uploaded with version",
            "description": "Dataset created from a form",
            "publication_type": PublicationType.NONE.name,
            "publication_doi": None,
            "dataset_doi": None,
            "tags": None,
        },
        get_authors=lambda: [],
        feature_models=[feature_model_form],
    )


def _write_temp_model(owner):
    temp_folder = owner.temp_folder()
    os.makedirs(temp_folder, exist_ok=True)
    with open(os.path.join(temp_folder, "model.uvl"), "wb") as handle:
        handle.write(b"features\n    Root\n")


def _dataset(user, title="Versioned dataset", doi=None):
    meta = DSMetaDataRepository().create(
        title=title,
        description="Dataset with versions",
        publication_type=PublicationType.NONE,
        dataset_doi=doi,
    )
    return DataSet(user_id=user.id, ds_meta_data_id=meta.id)


def _version(dataset, number, doi=None):
    return DatasetVersion(
        dataset_id=dataset.id,
        number=number,
        doi=doi,
        created_at=datetime(2026, 1, number, tzinfo=timezone.utc),
        published_at=datetime(2026, 2, number, tzinfo=timezone.utc) if doi else None,
    )


def _file(dataset, version, name, size=10):
    feature_model = FeatureModel(data_set_id=dataset.id, dataset_version_id=version.id)
    db.session.add(feature_model)
    db.session.flush()
    hubfile = Hubfile(name=name, checksum=f"checksum-{name}", size=size, feature_model_id=feature_model.id)
    db.session.add(hubfile)
    return hubfile


def test_versions_are_ordered_and_files_are_scoped_to_their_version(test_app, clean_database):
    with test_app.app_context():
        owner = _user()
        dataset = _dataset(owner)
        db.session.add(dataset)
        db.session.flush()

        first = _version(dataset, 1, doi="10.5072/version.1")
        second = _version(dataset, 2, doi="10.5072/version.2")
        db.session.add_all([first, second])
        db.session.flush()
        _file(dataset, first, "first.uvl", size=10)
        _file(dataset, second, "second.uvl", size=20)
        dataset.ds_meta_data.conceptrecid = 99
        dataset.ds_meta_data.concept_doi = "10.5072/concept.99"
        db.session.commit()

        loaded = db.session.get(BaseDataset, dataset.id)

        assert [version.number for version in loaded.dataset_versions] == [1, 2]
        assert loaded.latest_dataset_version().number == 2
        assert loaded.latest_published_dataset_version().number == 2
        assert [file.name for file in loaded.files_for_version(first)] == ["first.uvl"]
        assert [file.name for file in loaded.files_for_version()] == ["second.uvl"]
        # Only the current (latest published) version counts, since #38.
        assert loaded.get_files_count() == 1
        assert loaded.ds_meta_data.conceptrecid == 99
        assert loaded.ds_meta_data.concept_doi == "10.5072/concept.99"


def test_a_draft_version_does_not_replace_the_latest_published_one(test_app, clean_database):
    with test_app.app_context():
        owner = _user("draft-version@example.com")
        dataset = _dataset(owner, doi="10.5072/version.1")
        db.session.add(dataset)
        db.session.flush()

        published = _version(dataset, 1, doi=dataset.ds_meta_data.dataset_doi)
        draft = _version(dataset, 2)
        db.session.add_all([published, draft])
        db.session.flush()
        _file(dataset, published, "published.uvl")
        db.session.commit()

        loaded = db.session.get(BaseDataset, dataset.id)

        assert loaded.latest_dataset_version().number == 2
        assert loaded.latest_published_dataset_version().number == 1
        assert [file.name for file in loaded.files_for_version()] == ["published.uvl"]


def test_a_dataset_cannot_repeat_a_version_number(test_app, clean_database):
    with test_app.app_context():
        owner = _user("duplicate-version@example.com")
        dataset = _dataset(owner)
        db.session.add(dataset)
        db.session.flush()
        db.session.add(_version(dataset, 1))
        db.session.commit()

        db.session.add(_version(dataset, 1))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_create_from_form_creates_version_one_and_links_the_feature_models(
    test_app, clean_database, monkeypatch, tmp_path
):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))

    with test_app.app_context():
        owner = _user("form-version@example.com")
        _write_temp_model(owner)

        dataset = DataSetService().create_from_form(form=_form(), current_user=owner)

        loaded = db.session.get(BaseDataset, dataset.id)
        version = loaded.latest_dataset_version()

        assert version.number == 1
        assert version.doi is None
        assert version.published_at is None
        assert abs(version.created_at - datetime.now(timezone.utc).replace(tzinfo=None)) < timedelta(minutes=5)
        assert [feature_model.dataset_version_id for feature_model in loaded.feature_models] == [version.id]
        assert [file.name for file in loaded.files_for_version(version)] == ["model.uvl"]


def test_upload_dataset_stores_the_concept_doi_and_the_version_publication(
    test_app, clean_database, monkeypatch, tmp_path
):
    monkeypatch.setenv("WORKING_DIR", str(tmp_path))

    from app.features.zenodo.services import ZenodoService

    monkeypatch.setattr(
        ZenodoService,
        "create_new_deposition",
        lambda self, dataset: {"id": 42, "conceptrecid": 42},
    )
    monkeypatch.setattr(ZenodoService, "upload_file", lambda self, dataset, deposition_id, feature_model: {})
    monkeypatch.setattr(ZenodoService, "publish_deposition", lambda self, deposition_id: {})
    monkeypatch.setattr(
        ZenodoService,
        "get_deposition",
        lambda self, deposition_id: {
            "id": 42,
            "doi": "10.5072/fakenodo.42",
            "conceptdoi": "10.5072/fakenodo.concept.42",
        },
    )
    monkeypatch.setattr(DataSetService, "move_feature_models", lambda self, dataset: None)

    with test_app.app_context():
        owner = _user("upload-version@example.com")
        _write_temp_model(owner)

        result = DataSetService().upload_dataset(form=_form(), current_user=owner)

        assert result["status"] == "ok"
        loaded = DataSet.query.order_by(DataSet.id.desc()).first()
        assert loaded.ds_meta_data.deposition_id == 42
        assert loaded.ds_meta_data.conceptrecid == 42
        assert loaded.ds_meta_data.dataset_doi == "10.5072/fakenodo.42"
        assert loaded.ds_meta_data.concept_doi == "10.5072/fakenodo.concept.42"

        version = loaded.latest_dataset_version()
        assert version.number == 1
        assert version.deposition_id == 42
        assert version.doi == "10.5072/fakenodo.42"
        assert version.published_at is not None
