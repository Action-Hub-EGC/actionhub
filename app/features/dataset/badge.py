"""Embeddable SVG badge for a dataset, in the flat style of shields.io (#55).

The SVG is built here, with no external service, so the badge keeps working
offline and never leaks the visitor to a third party. Segments are drawn left
to right; each is as wide as its text plus some padding.
"""

from html import escape

MAX_TITLE_LENGTH = 30
HEIGHT = 20
# Average advance of an 11px Verdana glyph, plus the padding on both sides.
CHAR_WIDTH = 7
PADDING = 10

TITLE_COLOR = "#555"
DOI_COLOR = "#007ec6"
DOWNLOADS_COLOR = "#4c1"


def short_title(title: str) -> str:
    """The title cut to ``MAX_TITLE_LENGTH`` characters, ending in an ellipsis if cut."""
    if len(title) <= MAX_TITLE_LENGTH:
        return title
    return title[: MAX_TITLE_LENGTH - 1] + "…"


def _downloads_label(downloads: int) -> str:
    return f"{downloads} download" if downloads == 1 else f"{downloads} downloads"


def _markdown_text(value: str) -> str:
    """Escape the characters that would break a Markdown link label."""
    return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def markdown_badge_snippet(title: str, page_url: str, badge_url: str) -> str:
    """Ready-to-paste Markdown image link for a README (#57)."""
    return f"[![{_markdown_text(title)}]({badge_url})]({page_url})"


def html_badge_snippet(title: str, page_url: str, badge_url: str) -> str:
    """Ready-to-paste HTML image link for a website (#57)."""
    return f'<a href="{escape(page_url)}">' f'<img src="{escape(badge_url)}" alt="{escape(title)}">' "</a>"


def build_badge_svg(title: str, doi: str, downloads: int) -> str:
    """SVG badge with the short title, the DOI and the number of downloads."""
    segments = [
        (short_title(title), TITLE_COLOR),
        (doi, DOI_COLOR),
        (_downloads_label(downloads), DOWNLOADS_COLOR),
    ]

    rects, texts = [], []
    x = 0
    for text, color in segments:
        width = len(text) * CHAR_WIDTH + PADDING
        rects.append(f'<rect x="{x}" width="{width}" height="{HEIGHT}" fill="{color}"/>')
        texts.append(f'<text x="{x + width / 2}" y="14">{escape(text)}</text>')
        x += width
    total_width = x

    label = escape(" | ".join(text for text, _ in segments))
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{HEIGHT}" '
        f'role="img" aria-label="{label}">'
        f"<title>{label}</title>"
        '<linearGradient id="s" x2="0" y2="100%">'
        '<stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/>'
        "</linearGradient>"
        f'<clipPath id="r"><rect width="{total_width}" height="{HEIGHT}" rx="3" fill="#fff"/></clipPath>'
        f'<g clip-path="url(#r)">{"".join(rects)}'
        f'<rect width="{total_width}" height="{HEIGHT}" fill="url(#s)"/></g>'
        '<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">'
        f'{"".join(texts)}</g>'
        "</svg>"
    )
