"""Browser-facing URLs for depositions in Zenodo, the sandbox or fakenodo.

``ZENODO_API_URL`` points at the API. A browser must not receive that URL when
it names a container (``http://fakenodo:8000``): the hostname only resolves
inside the Compose network. ``ZENODO_RECORD_URL`` is the optional browser base;
when it is missing, the base is derived from the API URL:

- Zenodo and its sandbox use their public ``/records`` pages.
- Any other API (fakenodo, a proxy) is linked directly, so the link points at
  the service in use instead of at a hard-coded Zenodo host.

No URL is built when there is no deposition id: a dataset that has not been
published has no record to link.
"""

import os
from urllib.parse import urlparse

from flask import current_app, has_app_context

DEFAULT_API_URLS = {
    "production": "https://zenodo.org/api/deposit/depositions",
    "development": "https://sandbox.zenodo.org/api/deposit/depositions",
}

# Public record pages, keyed by API host.
ZENODO_RECORD_BASES = {
    "zenodo.org": "https://zenodo.org/records",
    "sandbox.zenodo.org": "https://sandbox.zenodo.org/records",
}


def default_api_url(app_env: str | None = None) -> str:
    """API URL used when ``ZENODO_API_URL`` is not set, as ``ZenodoService`` does."""
    app_env = app_env or os.getenv("FLASK_ENV", "development")
    return DEFAULT_API_URLS.get(app_env, DEFAULT_API_URLS["development"])


def api_url() -> str:
    """Configured deposition collection, without a trailing slash."""
    return (os.getenv("ZENODO_API_URL") or default_api_url()).rstrip("/")


def derive_record_base(api: str) -> str:
    """Browser base for a deposition, derived from its API collection URL."""
    host = (urlparse(api).hostname or "").lower()
    return ZENODO_RECORD_BASES.get(host, api.rstrip("/"))


def record_base_url() -> str:
    """Browser base for deposition links.

    ``ZENODO_RECORD_URL`` wins: the app config (easy to override in tests and
    deployments) and then the environment. Without it, the base follows the
    service that ``ZENODO_API_URL`` selects.
    """
    if has_app_context():
        configured = current_app.config.get("ZENODO_RECORD_URL")
        if configured:
            return configured.rstrip("/")

    configured = os.getenv("ZENODO_RECORD_URL")
    if configured:
        return configured.rstrip("/")

    return derive_record_base(api_url())


def record_url(deposition_id: int | None) -> str | None:
    """Public URL of a deposition, or ``None`` when it has no id."""
    if deposition_id is None:
        return None
    return f"{record_base_url()}/{deposition_id}"
