from flask import Flask
from flask_restful import Api
from splent_framework.assets.asset_registry import register_asset
from splent_framework.blueprints.base_blueprint import BaseBlueprint

from app.features.dataset.api import init_blueprint_api
from app.features.dataset.blocks import register_dataset_block
from app.features.explore.filters import register_uvl_filters

dataset_bp = BaseBlueprint("dataset", __name__, template_folder="templates")


api = Api(dataset_bp)
init_blueprint_api(api)


def init_feature(app: Flask) -> None:
    """Register assets and the type-specific block of a UVL dataset."""
    register_asset("js", "dataset.assets", subfolder="js", filename="scripts.js")
    register_dataset_block("uvl", "dataset/blocks/uvl.html")
    register_uvl_filters()
