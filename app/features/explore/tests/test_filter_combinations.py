"""Explore filter tests: each filter alone and in combinations on seeded data (#54)."""

import json
from datetime import datetime

import pytest

from app import db
from app.features.auth.models import User
from app.features.dataset.models import Author, DataSet, DSMetaData, PublicationType
from app.features.explore.services import ExploreService
from app.features.featuremodel.models import FeatureModel, FMMetaData
from app.features.workflow.models import WorkflowDataset, WorkflowVersion


def _seed_owner():
    user = User.query.filter_by(email="explore-seed@example.com").first()
    if user is None:
        user = User(email="explore-seed@example.com")
        user.set_password("secret")
        db.session.add(user)
        db.session.flush()
    return user


def _seed_uvl(
    title,
    description,
    author_name,
    tags,
    created_at,
    publication_type,
    doi,
    affiliation="Analytical Lab",
    orcid=None,
):
    meta = DSMetaData(
        title=title,
        description=description,
        publication_type=publication_type,
        dataset_doi=doi,
        tags=tags,
    )
    db.session.add(meta)
    db.session.flush()
    db.session.add(
        Author(
            name=author_name,
            affiliation=affiliation,
            orcid=orcid,
            ds_meta_data_id=meta.id,
        )
    )
    dataset = DataSet(user_id=_seed_owner().id, ds_meta_data_id=meta.id, created_at=created_at)
    fm_meta = FMMetaData(
        uvl_filename=f"{title.lower().replace(' ', '_')}.uvl",
        title=title,
        description=description,
        publication_type=publication_type,
        tags=tags,
    )
    db.session.add_all([dataset, fm_meta])
    db.session.flush()
    db.session.add(FeatureModel(data_set_id=dataset.id, fm_meta_data_id=fm_meta.id))
    db.session.commit()
    return dataset


def _seed_workflow(
    title,
    description,
    author_name,
    tags,
    created_at,
    doi,
    workflow_yaml,
    affiliation="Compiler Lab",
    orcid=None,
):
    meta = DSMetaData(
        title=title,
        description=description,
        publication_type=PublicationType.NONE,
        dataset_doi=doi,
        tags=tags,
    )
    db.session.add(meta)
    db.session.flush()
    db.session.add(
        Author(
            name=author_name,
            affiliation=affiliation,
            orcid=orcid,
            ds_meta_data_id=meta.id,
        )
    )
    dataset = WorkflowDataset(
        user_id=_seed_owner().id,
        ds_meta_data_id=meta.id,
        created_at=created_at,
        manifest_json=json.dumps({"name": title.lower().replace(" ", "-")}),
        validation_status="published",
    )
    db.session.add(dataset)
    db.session.flush()
    db.session.add(
        WorkflowVersion(
            workflow_dataset_id=dataset.id,
            manifest_json="{}",
            workflow_yaml=workflow_yaml,
        )
    )
    db.session.commit()
    return dataset


@pytest.fixture
def seeded_catalog(test_app, clean_database):
    """Seed five published datasets (3 UVL, 2 workflows) plus one hidden draft."""
    with test_app.app_context():
        uvl_alpha = _seed_uvl(
            title="Alpha SPL",
            description="Automotive software product line",
            author_name="Ada Lovelace",
            affiliation="Analytical Lab",
            orcid="0000-0001-1111-1111",
            tags="spl, automotive, java",
            created_at=datetime(2025, 1, 15, 10, 0, 0),
            publication_type=PublicationType.JOURNAL_ARTICLE,
            doi="10.1234/uvl-alpha",
        )
        uvl_beta = _seed_uvl(
            title="Beta IoT",
            description="Security feature model for IoT gateways",
            author_name="Alan Turing",
            affiliation="Bletchley",
            orcid="0000-0002-2222-2222",
            tags="iot, security",
            created_at=datetime(2025, 3, 20, 14, 0, 0),
            publication_type=PublicationType.CONFERENCE_PAPER,
            doi="10.1234/uvl-beta",
        )
        uvl_gamma = _seed_uvl(
            title="Gamma Automotive",
            description="Testing benchmarks for automotive models",
            author_name="Ada Lovelace",
            affiliation="Analytical Lab",
            orcid="0000-0001-1111-1111",
            tags="automotive, testing",
            created_at=datetime(2025, 6, 10, 9, 0, 0),
            publication_type=PublicationType.BOOK,
            doi="10.1234/uvl-gamma",
        )
        wf_ci = _seed_workflow(
            title="Python CI Pipeline",
            description="Automated pytest workflow",
            author_name="Grace Hopper",
            affiliation="Compiler Lab",
            orcid="0000-0003-3333-3333",
            tags="ci, python, security",
            created_at=datetime(2025, 4, 5, 12, 0, 0),
            doi="10.1234/wf-ci",
            workflow_yaml="name: ci\non: push\njobs:\n  test:\n    steps:\n      - uses: actions/setup-python@v5\n",
        )
        wf_deploy = _seed_workflow(
            title="Secure Release Deploy",
            description="Release pipeline for production",
            author_name="Ada Lovelace",
            affiliation="Analytical Lab",
            orcid="0000-0001-1111-1111",
            tags="deploy, security, ci",
            created_at=datetime(2025, 8, 1, 18, 0, 0),
            doi="10.1234/wf-deploy",
            workflow_yaml="name: deploy\non: push\njobs:\n  ship:\n    steps:\n      - uses: actions/checkout@v4\n",
        )
        _seed_uvl(
            title="Unpublished Draft",
            description="Hidden security draft",
            author_name="Ada Lovelace",
            tags="security, ci, automotive",
            created_at=datetime(2025, 9, 1, 8, 0, 0),
            publication_type=PublicationType.JOURNAL_ARTICLE,
            doi=None,
        )
        return {
            "uvl_alpha": uvl_alpha.id,
            "uvl_beta": uvl_beta.id,
            "uvl_gamma": uvl_gamma.id,
            "wf_ci": wf_ci.id,
            "wf_deploy": wf_deploy.id,
        }


@pytest.mark.service
@pytest.mark.parametrize(
    ("kwargs", "expected_keys"),
    [
        ({}, ["wf_deploy", "uvl_gamma", "wf_ci", "uvl_beta", "uvl_alpha"]),
        ({"sorting": "oldest"}, ["uvl_alpha", "uvl_beta", "wf_ci", "uvl_gamma", "wf_deploy"]),
        ({"query": "automotive"}, ["uvl_gamma", "uvl_alpha"]),
        ({"query": "setup-python"}, ["wf_ci"]),
        ({"author": "Ada"}, ["wf_deploy", "uvl_gamma", "uvl_alpha"]),
        ({"author": "Bletchley"}, ["uvl_beta"]),
        ({"author": "0000-0003-3333-3333"}, ["wf_ci"]),
        ({"start_date": "2025-05-01"}, ["wf_deploy", "uvl_gamma"]),
        ({"end_date": "2025-03-31"}, ["uvl_beta", "uvl_alpha"]),
        ({"start_date": "2025-03-01", "end_date": "2025-06-30"}, ["uvl_gamma", "wf_ci", "uvl_beta"]),
        ({"tags": ["iot"]}, ["uvl_beta"]),
        ({"tags": ["iot", "deploy"]}, ["wf_deploy", "uvl_beta"]),
        ({"publication_type": "article"}, ["uvl_alpha"]),
        ({"publication_type": "conferencepaper"}, ["uvl_beta"]),
        ({"dataset_type": "uvl"}, ["uvl_gamma", "uvl_beta", "uvl_alpha"]),
        ({"dataset_type": "workflow"}, ["wf_deploy", "wf_ci"]),
    ],
)
def test_each_filter_alone_returns_expected_seeded_datasets(test_app, seeded_catalog, kwargs, expected_keys):
    with test_app.app_context():
        results = ExploreService().filter(**kwargs)

    assert [dataset.id for dataset in results] == [seeded_catalog[key] for key in expected_keys]


@pytest.mark.service
@pytest.mark.parametrize(
    ("kwargs", "expected_keys"),
    [
        ({"author": "Ada", "dataset_type": "workflow"}, ["wf_deploy"]),
        ({"author": "Ada", "dataset_type": "uvl", "sorting": "oldest"}, ["uvl_alpha", "uvl_gamma"]),
        ({"tags": ["security"], "start_date": "2025-04-01", "end_date": "2025-08-31"}, ["wf_deploy", "wf_ci"]),
        ({"tags": ["security"], "dataset_type": "uvl", "author": "Turing"}, ["uvl_beta"]),
        ({"query": "automotive", "author": "Ada", "publication_type": "article"}, ["uvl_alpha"]),
        (
            {
                "query": "checkout",
                "dataset_type": "workflow",
                "author": "Ada",
                "tags": ["ci"],
                "start_date": "2025-07-01",
            },
            ["wf_deploy"],
        ),
        ({"author": "Grace", "dataset_type": "uvl"}, []),
        ({"tags": ["iot"], "start_date": "2025-06-01"}, []),
        ({"start_date": "2025-08-01", "end_date": "2025-01-01"}, []),
    ],
)
def test_filter_combinations_narrow_seeded_datasets_accurately(test_app, seeded_catalog, kwargs, expected_keys):
    with test_app.app_context():
        results = ExploreService().filter(**kwargs)

    assert [dataset.id for dataset in results] == [seeded_catalog[key] for key in expected_keys]


# ── HTTP integration tests: POST /explore & GET /explore?... ────────────


@pytest.mark.integration
@pytest.mark.parametrize(
    ("payload", "expected_keys"),
    [
        (
            {"query": "security", "dataset_type": "workflow", "sorting": "oldest"},
            ["wf_ci", "wf_deploy"],
        ),
        (
            {
                "author": "Ada",
                "tags": ["automotive", "ci"],
                "start_date": "2025-06-01",
                "end_date": "2025-08-31",
            },
            ["wf_deploy", "uvl_gamma"],
        ),
        (
            {
                "query": "automotive",
                "author": "Ada",
                "publication_type": "book",
                "dataset_type": "uvl",
            },
            ["uvl_gamma"],
        ),
        (
            {
                "query": "python",
                "author": "Ada",
                "dataset_type": "workflow",
            },
            [],
        ),
    ],
)
def test_post_explore_combinations_over_http(test_client, seeded_catalog, payload, expected_keys):
    response = test_client.post("/explore", json=payload)

    assert response.status_code == 200
    body = response.get_json()
    assert [item["id"] for item in body] == [seeded_catalog[key] for key in expected_keys]


@pytest.mark.integration
def test_get_explore_preserves_combined_url_parameters(test_client):
    response = test_client.get(
        "/explore?query=security&author=Ada&start_date=2025-01-01&end_date=2025-12-31"
        "&tags=ci,security&dataset_type=workflow"
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "security" in html
    assert "Ada" in html
    assert "2025-01-01" in html
    assert "2025-12-31" in html
    assert "ci,security" in html
    assert "workflow" in html
