"""Unit tests for the per-dataset counter service (#67).

The repository is replaced by a fake, so these tests need neither the Flask
app nor the database. ``test_counter_repository.py`` checks the queries.
"""

import pytest

from app.features.metrics.repositories import DatasetCounterRepository
from app.features.metrics.services import DatasetCounterService

pytestmark = pytest.mark.unit


class FakeCounterRepository:
    def __init__(self, counts=None):
        self._counts = counts or {}
        self.calls = []

    def counts(self, dataset_ids):
        ids = list(dataset_ids)
        self.calls.append(ids)
        return {dataset_id: self._counts[dataset_id] for dataset_id in ids if dataset_id in self._counts}


def test_counts_returns_the_downloads_and_views_of_a_dataset():
    service = DatasetCounterService(FakeCounterRepository({7: {"downloads": 3, "views": 10}}))

    assert service.counts(7) == {"downloads": 3, "views": 10}


def test_counts_of_a_dataset_without_activity_are_zero():
    service = DatasetCounterService(FakeCounterRepository())

    assert service.counts(7) == {"downloads": 0, "views": 0}


def test_counts_fill_in_a_missing_metric_with_zero():
    service = DatasetCounterService(FakeCounterRepository({7: {"views": 4}, 8: {"downloads": 2}}))

    assert service.counts(7) == {"downloads": 0, "views": 4}
    assert service.counts(8) == {"downloads": 2, "views": 0}


def test_counts_for_many_returns_every_requested_dataset_in_one_call():
    repository = FakeCounterRepository({1: {"downloads": 1, "views": 2}, 3: {"downloads": 5, "views": 5}})
    service = DatasetCounterService(repository)

    counts = service.counts_for_many([3, 1, 2])

    assert counts == {
        3: {"downloads": 5, "views": 5},
        1: {"downloads": 1, "views": 2},
        2: {"downloads": 0, "views": 0},
    }
    assert list(counts) == [3, 1, 2]
    assert repository.calls == [[3, 1, 2]]


def test_counts_for_many_asks_once_for_repeated_ids_and_accepts_generators():
    repository = FakeCounterRepository({1: {"downloads": 1, "views": 1}})
    service = DatasetCounterService(repository)

    counts = service.counts_for_many(dataset_id for dataset_id in (1, 1, 2))

    assert counts == {1: {"downloads": 1, "views": 1}, 2: {"downloads": 0, "views": 0}}
    assert repository.calls == [[1, 2]]


def test_counts_for_many_of_nothing_does_not_query():
    repository = FakeCounterRepository()

    assert DatasetCounterService(repository).counts_for_many([]) == {}
    assert repository.calls == []


def test_counts_are_plain_integers():
    # Database drivers may hand back Decimal or long values; templates and JSON
    # need plain ints.
    service = DatasetCounterService(FakeCounterRepository({1: {"downloads": 2.0, "views": True}}))

    counts = service.counts(1)

    assert counts == {"downloads": 2, "views": 1}
    assert all(type(value) is int for value in counts.values())


def test_the_default_repository_is_the_database_one():
    assert isinstance(DatasetCounterService().repository, DatasetCounterRepository)
