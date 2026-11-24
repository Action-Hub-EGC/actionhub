"""HTTP integration tests for explore via the Flask test client."""

import json
from datetime import datetime

import pytest

from app import db
from app.features.auth.models import User
from app.features.dataset.models import Author, DataSet, DSDownloadRecord, DSMetaData, DSViewRecord, PublicationType
from app.features.featuremodel.models import FeatureModel, FMMetaData
from app.features.workflow.models import WorkflowDataset, WorkflowVersion

pytestmark = pytest.mark.integration


def _owner():
    user = User.query.filter_by(email="owner@example.com").first()
    if user is None:
        user = User(email="owner@example.com")
        user.set_password("ownerpass")
        db.session.add(user)
        db.session.flush()
    return user


def _make_dataset(title, description, author_name, tags, created_at, publication_type):
    ds_meta_data = DSMetaData(
        title=title,
        description=description,
        publication_type=publication_type,
        dataset_doi="10.1234/default",
        tags=tags,
    )
    db.session.add(ds_meta_data)
    db.session.flush()
    db.session.add(Author(name=author_name, affiliation="Some University", ds_meta_data_id=ds_meta_data.id))
    dataset = DataSet(user_id=_owner().id, ds_meta_data_id=ds_meta_data.id, created_at=created_at)
    fm_meta_data = FMMetaData(
        uvl_filename=f"{title.lower().replace(' ', '_')}.uvl",
        title=title,
        description=description,
        publication_type=publication_type,
        tags=tags,
    )
    db.session.add_all([dataset, fm_meta_data])
    db.session.flush()
    db.session.add(FeatureModel(data_set_id=dataset.id, fm_meta_data_id=fm_meta_data.id))
    db.session.commit()
    return dataset


def _make_workflow(title, description, author_name, tags, created_at):
    ds_meta_data = DSMetaData(
        title=title,
        description=description,
        publication_type=PublicationType.NONE,
        dataset_doi=f"10.1234/{title.lower().replace(' ', '-')}",
        tags=tags,
    )
    db.session.add(ds_meta_data)
    db.session.flush()
    db.session.add(Author(name=author_name, affiliation="Some University", ds_meta_data_id=ds_meta_data.id))
    dataset = WorkflowDataset(
        user_id=_owner().id,
        ds_meta_data_id=ds_meta_data.id,
        created_at=created_at,
        manifest_json="{}",
        validation_status="published",
    )
    db.session.add(dataset)
    db.session.flush()
    db.session.add(
        WorkflowVersion(
            workflow_dataset_id=dataset.id,
            manifest_json="{}",
            workflow_yaml="name: deploy\non: push\njobs:\n  deploy:\n    steps:\n      - uses: actions/checkout@v4\n",
            metadata_json=json.dumps(
                {
                    "name": "deploy",
                    "triggers": ["push"],
                    "jobs": [],
                    "runners": ["ubuntu-latest"],
                    "actions": ["actions/checkout@v4"],
                    "reusable_workflows": [],
                }
            ),
        )
    )
    db.session.commit()
    return dataset


def _seed_corpus(test_app):
    with test_app.app_context():
        _make_dataset(
            "Smart Home",
            "home automation product line",
            "Alice Doe",
            "iot,home",
            datetime(2024, 1, 1),
            PublicationType.JOURNAL_ARTICLE,
        )
        _make_dataset(
            "Car Configurator",
            "vehicle variability",
            "Bob Roe",
            "automotive",
            datetime(2024, 2, 1),
            PublicationType.BOOK,
        )
        _make_dataset(
            "Home Banking",
            "finance product line",
            "Carol Poe",
            "finance",
            datetime(2024, 3, 1),
            PublicationType.JOURNAL_ARTICLE,
        )


def test_explore_page_renders_the_search_form(test_client):
    response = test_client.get("/explore")
    assert response.status_code == 200
    assert b"<b>Explore</b>" in response.data
    assert b'name="query"' in response.data
    assert b'name="publication_type"' in response.data
    assert b'name="author"' in response.data
    assert b'name="start_date"' in response.data
    assert b'name="end_date"' in response.data
    assert b'name="tags"' in response.data


def test_explore_page_reads_the_author_from_the_url(test_client):
    response = test_client.get("/explore?author=Alice")

    assert response.status_code == 200
    assert b'value="Alice"' in response.data


def test_explore_page_reads_the_date_range_from_the_url(test_client):
    response = test_client.get("/explore?start_date=2024-01-01&end_date=2024-12-31")

    assert response.status_code == 200
    assert b'value="2024-01-01"' in response.data
    assert b'value="2024-12-31"' in response.data


def test_explore_page_reads_the_tags_from_the_url(test_client):
    response = test_client.get("/explore?tags=iot,home")

    assert response.status_code == 200
    assert b'value="iot,home"' in response.data


def test_explore_page_reads_the_dataset_type_from_the_url(test_client):
    response = test_client.get("/explore?dataset_type=workflow")

    assert response.status_code == 200
    assert b'id="dataset_type"' in response.data
    assert b'value="workflow" selected' in response.data


def test_search_includes_workflow_datasets_and_filters_by_type(test_app, test_client):
    with test_app.app_context():
        _seed_corpus(test_app)
        workflow = _make_workflow(
            "Deploy Pipeline",
            "deploys the application",
            "Dana Doe",
            "ci",
            datetime(2024, 6, 1),
        )
        db.session.add(DSViewRecord(dataset_id=workflow.id, view_cookie="workflow-view"))
        db.session.add(DSDownloadRecord(dataset_id=workflow.id, download_cookie="workflow-download"))
        db.session.commit()

    all_results = test_client.post("/explore", json={}).get_json()
    titles = {dataset["title"] for dataset in all_results}
    assert "Deploy Pipeline" in titles
    assert {"Smart Home", "Car Configurator", "Home Banking"}.issubset(titles)
    workflow_result = next(dataset for dataset in all_results if dataset["title"] == "Deploy Pipeline")
    assert workflow_result["type"] == "workflow"
    assert workflow_result["counts"] == {"downloads": 1, "views": 1}

    only_workflows = test_client.post("/explore", json={"dataset_type": "workflow"}).get_json()
    assert [dataset["title"] for dataset in only_workflows] == ["Deploy Pipeline"]

    only_uvl = test_client.post("/explore", json={"dataset_type": "uvl"}).get_json()
    assert {dataset["title"] for dataset in only_uvl} == {"Smart Home", "Car Configurator", "Home Banking"}

    # The workflow YAML participates in the free-text search.
    by_action = test_client.post("/explore", json={"query": "checkout"}).get_json()
    assert [dataset["title"] for dataset in by_action] == ["Deploy Pipeline"]


def test_search_returns_only_the_matching_datasets(test_app, test_client):
    _seed_corpus(test_app)
    response = test_client.post("/explore", json={"query": "alice"})
    assert response.status_code == 200
    payload = response.get_json()
    assert [dataset["title"] for dataset in payload] == ["Smart Home"]
    assert [author["name"] for author in payload[0]["authors"]] == ["Alice Doe"]
    assert payload[0]["tags"] == ["iot", "home"]


def test_search_with_an_empty_payload_returns_every_dataset_newest_first(test_app, test_client):
    _seed_corpus(test_app)
    response = test_client.post("/explore", json={})
    assert response.status_code == 200
    assert [dataset["title"] for dataset in response.get_json()] == [
        "Home Banking",
        "Car Configurator",
        "Smart Home",
    ]


def test_search_honours_sorting_and_publication_type(test_app, test_client):
    _seed_corpus(test_app)

    oldest = test_client.post("/explore", json={"query": "home", "sorting": "oldest"})
    assert [dataset["title"] for dataset in oldest.get_json()] == ["Smart Home", "Home Banking"]

    books = test_client.post("/explore", json={"query": "", "publication_type": "book"})
    assert [dataset["title"] for dataset in books.get_json()] == ["Car Configurator"]


def test_search_honours_author(test_app, test_client):
    _seed_corpus(test_app)

    response = test_client.post("/explore", json={"author": "alice"})
    assert response.status_code == 200
    assert [dataset["title"] for dataset in response.get_json()] == ["Smart Home"]

    response = test_client.post("/explore", json={"author": "Some University"})
    assert len(response.get_json()) == 3


def test_search_honours_the_date_range(test_app, test_client):
    _seed_corpus(test_app)

    response = test_client.post(
        "/explore",
        json={"start_date": "2024-01-15", "end_date": "2024-02-15"},
    )
    assert response.status_code == 200
    assert [dataset["title"] for dataset in response.get_json()] == ["Car Configurator"]


def test_search_honours_one_or_several_tags(test_app, test_client):
    _seed_corpus(test_app)

    one_tag = test_client.post("/explore", json={"tags": ["iot"]})
    assert [dataset["title"] for dataset in one_tag.get_json()] == ["Smart Home"]

    several_tags = test_client.post("/explore", json={"tags": ["automotive", "finance"]})
    assert [dataset["title"] for dataset in several_tags.get_json()] == [
        "Home Banking",
        "Car Configurator",
    ]

    no_match = test_client.post("/explore", json={"tags": ["nonexistent"]})
    assert no_match.get_json() == []


def test_search_returns_an_empty_list_when_nothing_matches(test_app, test_client):
    _seed_corpus(test_app)
    response = test_client.post("/explore", json={"query": "nothingmatchesthis"})
    assert response.status_code == 200
    assert response.get_json() == []


def test_search_without_a_json_body_behaves_like_an_unfiltered_search(test_app, test_client):
    _seed_corpus(test_app)
    response = test_client.post("/explore")
    assert response.status_code == 200
    assert [dataset["title"] for dataset in response.get_json()] == [
        "Home Banking",
        "Car Configurator",
        "Smart Home",
    ]


def test_search_includes_the_counts_of_each_dataset(test_app, test_client):
    _seed_corpus(test_app)
    with test_app.app_context():
        smart_home = DSMetaData.query.filter_by(title="Smart Home").one().data_set
        db.session.add(DSDownloadRecord(dataset_id=smart_home.id, download_cookie="cookie-a"))
        db.session.add(DSViewRecord(dataset_id=smart_home.id, view_cookie="cookie-a"))
        db.session.add(DSViewRecord(dataset_id=smart_home.id, view_cookie="cookie-b"))
        db.session.commit()

    results = test_client.post("/explore", json={}).get_json()

    counts = {dataset["title"]: dataset["counts"] for dataset in results}
    assert counts["Smart Home"] == {"downloads": 1, "views": 2}
    assert counts["Car Configurator"] == {"downloads": 0, "views": 0}
