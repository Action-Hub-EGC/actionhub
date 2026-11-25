"""Copy box with Markdown and HTML badge snippets (#57)."""

import html

import pytest

from app.features.dataset.badge import html_badge_snippet, markdown_badge_snippet
from app.features.dataset.tests.test_integration import _make_dataset, _signup

pytestmark = pytest.mark.integration


def test_markdown_snippet_escapes_the_alt_text():
    snippet = markdown_badge_snippet(
        "Data [v1]",
        "https://hub.test/doi/10.1234/data",
        "https://hub.test/doi/10.1234/data/badge.svg",
    )

    assert snippet == (
        "[![Data \\[v1\\]](https://hub.test/doi/10.1234/data/badge.svg)]" "(https://hub.test/doi/10.1234/data)"
    )


def test_html_snippet_escapes_title_and_urls():
    snippet = html_badge_snippet(
        'Data "quoted" <script>',
        "https://hub.test/doi/10.1234/data?a=1&b=2",
        "https://hub.test/doi/10.1234/data/badge.svg",
    )

    assert snippet.startswith('<a href="https://hub.test/doi/10.1234/data?a=1&amp;b=2">')
    assert 'alt="Data &quot;quoted&quot; &lt;script&gt;"' in snippet
    assert "</a>" in snippet


def test_dataset_page_shows_copyable_markdown_and_html(test_client):
    user_id = _signup(test_client, email="embed@example.com")
    with test_client.application.app_context():
        _make_dataset(user_id, title="Embeddable dataset", doi="10.1234/embed")

    body = html.unescape(test_client.get("/doi/10.1234/embed/").get_data(as_text=True))

    assert 'id="embed-badge"' in body
    assert 'id="embed-markdown"' in body
    assert 'id="embed-html"' in body
    assert "[![Embeddable dataset](" in body
    assert "/doi/10.1234/embed/badge.svg" in body
    assert "/doi/10.1234/embed)" in body
    assert '<a href="' in body and '<img src="' in body
    assert "copyValue('embed-markdown')" in body
    assert "copyValue('embed-html')" in body


def test_unpublished_dataset_has_no_badge_box(test_client):
    user_id = _signup(test_client, email="embed-draft@example.com")
    with test_client.application.app_context():
        dataset_id = _make_dataset(user_id, title="Draft dataset").id

    body = test_client.get(f"/dataset/unsynchronized/{dataset_id}/").get_data(as_text=True)

    assert "Embed badge" not in body
    assert 'id="embed-markdown"' not in body


def test_badge_embed_is_none_without_a_doi(test_app):
    with test_app.app_context():
        from app.features.auth.repositories import UserRepository

        owner = UserRepository().create(email="embed-model@example.com", password="secret")
        dataset = _make_dataset(owner.id, title="No DOI")

        assert dataset.get_badge_url() is None
        assert dataset.get_badge_embed() is None
