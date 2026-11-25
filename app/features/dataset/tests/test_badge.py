"""Dynamic SVG badge with the short title, DOI and downloads of a dataset (#55)."""

import xml.etree.ElementTree as ET

import pytest

from app import db
from app.features.dataset.badge import build_badge_svg
from app.features.dataset.models import DSDownloadRecord, DSViewRecord
from app.features.dataset.repositories import DOIMappingRepository
from app.features.dataset.tests.test_integration import _make_dataset, _signup

SVG_NS = "{http://www.w3.org/2000/svg}"


def _texts(svg: str) -> list[str]:
    """Visible texts of the badge, left to right. Parsing also proves the SVG is well-formed."""
    root = ET.fromstring(svg)
    assert root.tag == f"{SVG_NS}svg"
    return [node.text for node in root.iter(f"{SVG_NS}text")]


@pytest.mark.unit
def test_badge_shows_title_doi_and_downloads():
    svg = build_badge_svg(title="Lint workflow", doi="10.1234/lint", downloads=12)

    assert _texts(svg) == ["Lint workflow", "10.1234/lint", "12 downloads"]


@pytest.mark.unit
def test_badge_uses_singular_for_one_download():
    svg = build_badge_svg(title="Lint workflow", doi="10.1234/lint", downloads=1)

    assert _texts(svg)[-1] == "1 download"


@pytest.mark.unit
def test_badge_shortens_a_long_title():
    svg = build_badge_svg(
        title="Continuous integration workflow for Python packages",
        doi="10.1234/ci",
        downloads=0,
    )

    assert _texts(svg)[0] == "Continuous integration workfl…"
    assert "Python packages" not in svg


@pytest.mark.unit
def test_badge_keeps_a_title_at_the_limit_untouched():
    title = "Thirty characters long title!!"
    assert len(title) == 30

    assert _texts(build_badge_svg(title=title, doi="10.1234/x", downloads=0))[0] == title


@pytest.mark.unit
def test_badge_escapes_markup_in_the_title():
    svg = build_badge_svg(title='<script>x</script> & "co"', doi="10.1234/x", downloads=0)

    root = ET.fromstring(svg)
    assert root.find(f".//{SVG_NS}script") is None
    assert _texts(svg)[0] == '<script>x</script> & "co"'


@pytest.mark.unit
def test_badge_grows_with_its_text():
    short = ET.fromstring(build_badge_svg(title="A", doi="10.1/a", downloads=0))
    long = ET.fromstring(build_badge_svg(title="A much longer title", doi="10.1234/a-long-doi", downloads=0))

    assert float(long.get("width")) > float(short.get("width"))


def _add_downloads(dataset_id, count):
    for n in range(count):
        db.session.add(DSDownloadRecord(dataset_id=dataset_id, download_cookie=f"badge-download-{n}"))
    db.session.commit()


@pytest.mark.integration
def test_badge_route_serves_the_svg_with_the_counter_downloads(test_client):
    user_id = _signup(test_client, email="badge@example.com")
    with test_client.application.app_context():
        dataset = _make_dataset(user_id, title="Badged dataset", doi="10.1234/badged")
        _add_downloads(dataset.id, 3)

    response = test_client.get("/doi/10.1234/badged/badge.svg")

    assert response.status_code == 200
    assert response.mimetype == "image/svg+xml"
    assert _texts(response.get_data(as_text=True)) == ["Badged dataset", "10.1234/badged", "3 downloads"]


@pytest.mark.integration
def test_badge_route_does_not_count_a_view(test_client):
    user_id = _signup(test_client, email="badge-views@example.com")
    with test_client.application.app_context():
        dataset_id = _make_dataset(user_id, title="Embedded dataset", doi="10.1234/embedded").id

    response = test_client.get("/doi/10.1234/embedded/badge.svg")

    assert response.status_code == 200
    assert "view_cookie" not in response.headers.get("Set-Cookie", "")
    with test_client.application.app_context():
        assert DSViewRecord.query.filter_by(dataset_id=dataset_id).count() == 0


@pytest.mark.integration
def test_badge_route_redirects_a_superseded_doi(test_client):
    user_id = _signup(test_client, email="badge-old@example.com")
    with test_client.application.app_context():
        _make_dataset(user_id, title="Moved dataset", doi="10.5678/moved")
        DOIMappingRepository().create(dataset_doi_old="10.1234/moved-old", dataset_doi_new="10.5678/moved")

    response = test_client.get("/doi/10.1234/moved-old/badge.svg", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/doi/10.5678/moved/badge.svg")


@pytest.mark.integration
def test_badge_route_404s_for_an_unknown_doi(test_client):
    assert test_client.get("/doi/10.1234/no-such-dataset/badge.svg").status_code == 404
