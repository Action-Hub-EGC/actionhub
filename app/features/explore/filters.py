"""Type-specific filters for the explorer (#52).

Each dataset feature registers its own filters. The repository applies them
only when the corresponding query parameter has a value; the template renders
the registered fields from the same registry, so a new type can add a filter
without editing the explore form by hand.
"""

from dataclasses import dataclass
from typing import Callable

from sqlalchemy import Integer, cast, or_

FilterApply = Callable[[object, str], object]


@dataclass(frozen=True)
class ExploreFilter:
    name: str
    label: str
    dataset_type: str
    kind: str = "text"
    options: tuple[tuple[str, str], ...] = ()
    placeholder: str = ""
    apply: FilterApply | None = None


_FILTERS: dict[str, list[ExploreFilter]] = {}


def register_explore_filter(dataset_type: str, explore_filter: ExploreFilter) -> None:
    """Register *explore_filter* for a dataset type, ignoring duplicates."""
    if not dataset_type or explore_filter is None:
        raise ValueError("dataset_type and filter are required")
    filters = _FILTERS.setdefault(str(dataset_type), [])
    if not any(existing.name == explore_filter.name for existing in filters):
        filters.append(explore_filter)


def filters_for(dataset_type: str | None = None) -> list[ExploreFilter]:
    """Registered filters, optionally only those of one dataset type."""
    if dataset_type in (None, "", "any") or str(dataset_type) not in _FILTERS:
        return [item for filters in _FILTERS.values() for item in filters]
    return list(_FILTERS.get(str(dataset_type), []))


def _number_filter(field: str, comparison: str) -> FilterApply:
    def apply(query, value):
        try:
            number = int(str(value).strip())
        except (TypeError, ValueError):
            return query
        from app.features.dataset.models import DSMetrics

        column = cast(getattr(DSMetrics, field), Integer)
        expression = column >= number if comparison == "min" else column <= number
        return query.filter(expression)

    return apply


def _contains_filter() -> FilterApply:
    def apply(query, value):
        term = str(value).strip()
        if not term:
            return query
        from app.features.workflow.models import WorkflowVersion

        # Metadata stores the values as JSON strings; the YAML is a fallback for
        # rows created before metadata extraction.
        quoted = f'%"{term}"%'
        return query.filter(
            or_(
                WorkflowVersion.metadata_json.ilike(quoted),
                WorkflowVersion.workflow_yaml.ilike(f"%{term}%"),
            )
        )

    return apply


def _grade_filter(query, value):
    from app.features.workflow.models import WorkflowDataset

    grade = str(value).strip().upper()
    if not grade:
        return query
    return query.filter(WorkflowDataset.grade == grade)


def register_uvl_filters() -> None:
    """UVL filters: number of models and features stored in ``DSMetrics``."""
    for name, field, comparison, label in (
        ("models_min", "number_of_models", "min", "UVL · Minimum models"),
        ("models_max", "number_of_models", "max", "UVL · Maximum models"),
        ("features_min", "number_of_features", "min", "UVL · Minimum features"),
        ("features_max", "number_of_features", "max", "UVL · Maximum features"),
    ):
        register_explore_filter(
            "uvl",
            ExploreFilter(
                name=name,
                label=label,
                dataset_type="uvl",
                kind="number",
                apply=_number_filter(field, comparison),
            ),
        )


def register_workflow_filters() -> None:
    """Workflow filters: grade, trigger, runner and used action."""
    register_explore_filter(
        "workflow",
        ExploreFilter(
            name="grade",
            label="Workflow · Security grade",
            dataset_type="workflow",
            kind="select",
            options=tuple((grade, grade) for grade in ("A", "B", "C", "D", "E", "F")),
            apply=_grade_filter,
        ),
    )
    for name, label in (
        ("trigger", "Workflow · Trigger"),
        ("runner", "Workflow · Runner"),
        ("action", "Workflow · Action"),
    ):
        register_explore_filter(
            "workflow",
            ExploreFilter(
                name=name,
                label=label,
                dataset_type="workflow",
                kind="text",
                placeholder="push, ubuntu-latest, actions/checkout@v4...",
                apply=_contains_filter(),
            ),
        )
