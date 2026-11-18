"""Model tests for the BaseDataset / UVLDataset split (#11)."""

import pytest

from app import db
from app.features.auth.repositories import UserRepository
from app.features.dataset.models import BaseDataset, DataSet, DSMetaData, PublicationType, UVLDataset
from app.features.featuremodel.models import FeatureModel
from app.features.hubfile.models import Hubfile

pytestmark = pytest.mark.repository


def make_user(email):
    return UserRepository().create(email=email, password="secret")


def make_meta(title):
    meta = DSMetaData(
        title=title,
        description=f"Description for {title}",
        publication_type=PublicationType.NONE,
    )
    db.session.add(meta)
    db.session.flush()
    return meta


def test_data_set_alias_points_to_uvl_dataset():
    assert DataSet is UVLDataset
    assert issubclass(UVLDataset, BaseDataset)


def test_new_data_set_is_a_uvl_dataset_by_default(test_app, test_client):
    with test_app.app_context():
        user = make_user("model-default@example.com")
        meta = make_meta("default")

        dataset = DataSet(user_id=user.id, ds_meta_data_id=meta.id)

        assert isinstance(dataset, UVLDataset)
        assert dataset.type == "uvl"


def test_base_dataset_query_returns_the_uvl_subclass(test_app, test_client):
    with test_app.app_context():
        user = make_user("model-polymorphic@example.com")
        meta = make_meta("polymorphic")
        dataset = UVLDataset(user_id=user.id, ds_meta_data_id=meta.id)
        db.session.add(dataset)
        db.session.commit()

        loaded = db.session.get(BaseDataset, dataset.id)

        assert isinstance(loaded, UVLDataset)
        assert loaded.type == "uvl"
        assert loaded.name() == "polymorphic"


def test_uvl_files_are_counted_through_the_base_interface(test_app, test_client):
    with test_app.app_context():
        user = make_user("model-files@example.com")
        meta = make_meta("files")
        dataset = UVLDataset(user_id=user.id, ds_meta_data_id=meta.id)
        db.session.add(dataset)
        db.session.flush()

        version = FeatureModel(data_set_id=dataset.id)
        db.session.add(version)
        db.session.flush()
        db.session.add(Hubfile(name="model.uvl", checksum="abc", size=42, feature_model_id=version.id))
        db.session.commit()

        loaded = db.session.get(BaseDataset, dataset.id)

        assert loaded.get_files_count() == 1
        assert loaded.get_file_total_size() == 42
        assert [file.name for file in loaded.files()] == ["model.uvl"]
        with test_app.test_request_context("/"):
            assert loaded.to_dict()["files_count"] == 1
