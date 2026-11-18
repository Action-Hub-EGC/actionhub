from datetime import datetime, timezone

import pytest

from app.features.metrics.utils import as_utc

pytestmark = pytest.mark.unit


def test_as_utc_attaches_utc_to_naive_values():
    assert as_utc(datetime(2024, 1, 1, 12)) == datetime(2024, 1, 1, 12, tzinfo=timezone.utc)


def test_as_utc_converts_aware_values():
    value = datetime(2024, 1, 1, 12, tzinfo=timezone.utc).astimezone(timezone.utc)

    assert as_utc(value) == value


def test_as_utc_keeps_none():
    assert as_utc(None) is None
