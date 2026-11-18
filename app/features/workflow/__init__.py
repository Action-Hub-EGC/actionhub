from flask import Flask
from splent_framework.blueprints.base_blueprint import BaseBlueprint

workflow_bp = BaseBlueprint("workflow", __name__, template_folder="templates")


def init_feature(app: Flask) -> None:
    """Workflow feature lifecycle hook. Routes and assets arrive in #13."""
