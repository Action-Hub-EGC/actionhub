from flask import Flask
from splent_framework.blueprints.base_blueprint import BaseBlueprint
from splent_framework.nav.nav_registry import register_nav_item

workflow_bp = BaseBlueprint("workflow", __name__, template_folder="templates")


def init_feature(app: Flask) -> None:
    """Register the workflow section in the main navigation."""
    register_nav_item("workflows", "Workflows", "/workflow", order=60, icon="git-branch")
