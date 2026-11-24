"""Registry of type-specific dataset blocks (#20)."""

import pytest

from app.features.dataset.blocks import blocks_for, register_dataset_block, registered_blocks

pytestmark = pytest.mark.unit


def test_uvl_and_workflow_register_their_own_block(test_app):
    assert "dataset/blocks/uvl.html" in blocks_for("uvl")
    assert "workflow/blocks/workflow.html" in blocks_for("workflow")


def test_registering_the_same_block_twice_does_not_duplicate_it(test_app):
    register_dataset_block("registry-test-type", "tests/blocks/one.html")
    register_dataset_block("registry-test-type", "tests/blocks/one.html")

    assert blocks_for("registry-test-type") == ["tests/blocks/one.html"]


def test_a_new_type_can_register_a_block_without_touching_the_common_page(test_app):
    register_dataset_block("registry-new-type", "tests/blocks/new.html")

    assert blocks_for("registry-new-type") == ["tests/blocks/new.html"]
    assert "registry-new-type" in registered_blocks()
    assert blocks_for("registry-unknown-type") == []


def test_blank_registration_is_rejected():
    with pytest.raises(ValueError):
        register_dataset_block("", "tests/blocks/one.html")
    with pytest.raises(ValueError):
        register_dataset_block("uvl", "")
