"""Type-specific blocks for the common dataset page (#20).

The common page renders the blocks registered for ``dataset.type``. A new
dataset type only has to call ``register_dataset_block`` from its feature's
``init_feature`` and ship the template; the common template is never edited.
"""

_BLOCKS: dict[str, list[str]] = {}


def register_dataset_block(dataset_type: str, template: str) -> None:
    """Append *template* to the blocks shown for *dataset_type*.

    Registration is idempotent for a given pair, so reloading a feature does
    not duplicate its block.
    """
    if not dataset_type or not template:
        raise ValueError("dataset_type and template are required")
    templates = _BLOCKS.setdefault(str(dataset_type), [])
    if template not in templates:
        templates.append(template)


def blocks_for(dataset_type: str) -> list[str]:
    """Templates registered for *dataset_type*, in registration order."""
    return list(_BLOCKS.get(str(dataset_type), []))


def registered_blocks() -> dict[str, list[str]]:
    """Copy of the registry, useful for diagnostics and tests."""
    return {dataset_type: list(templates) for dataset_type, templates in _BLOCKS.items()}
