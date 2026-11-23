"""Unit tests for the browser-facing Zenodo/fakenodo record URLs (#32)."""

import pytest

from app.features.zenodo.urls import derive_record_base, record_url

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("api", "expected"),
    [
        ("https://zenodo.org/api/deposit/depositions", "https://zenodo.org/records"),
        ("https://sandbox.zenodo.org/api/deposit/depositions", "https://sandbox.zenodo.org/records"),
        ("http://fakenodo:8000/api/deposit/depositions", "http://fakenodo:8000/api/deposit/depositions"),
        ("http://localhost:8000/api/deposit/depositions/", "http://localhost:8000/api/deposit/depositions"),
    ],
)
def test_record_base_follows_the_api_host(api, expected):
    assert derive_record_base(api) == expected


def test_record_url_uses_the_configured_browser_base(test_app, monkeypatch):
    monkeypatch.delenv("ZENODO_RECORD_URL", raising=False)
    monkeypatch.setitem(test_app.config, "ZENODO_RECORD_URL", "http://localhost:8000/api/deposit/depositions")

    with test_app.app_context():
        assert record_url(7) == "http://localhost:8000/api/deposit/depositions/7"


def test_record_url_falls_back_to_the_selected_zenodo_service(test_app, monkeypatch):
    monkeypatch.delenv("ZENODO_RECORD_URL", raising=False)
    monkeypatch.delenv("ZENODO_API_URL", raising=False)
    monkeypatch.setitem(test_app.config, "ZENODO_RECORD_URL", None)

    with test_app.app_context():
        assert record_url(5) == "https://sandbox.zenodo.org/records/5"


def test_record_url_is_none_without_a_deposition():
    assert record_url(None) is None
