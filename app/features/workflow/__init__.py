from flask import Flask
from splent_framework.blueprints.base_blueprint import BaseBlueprint
from splent_framework.nav.nav_registry import register_nav_item

from app.features.dataset.blocks import register_dataset_block
from app.features.explore.filters import register_workflow_filters

workflow_bp = BaseBlueprint("workflow", __name__, template_folder="templates")


def init_feature(app: Flask) -> None:
    """Register the workflow navigation entry and its dataset block."""
    register_nav_item("workflows", "Workflows", "/workflow", order=60, icon="git-branch")
    register_dataset_block("workflow", "workflow/blocks/workflow.html")
    register_workflow_filters()
