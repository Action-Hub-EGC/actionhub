from flask import jsonify, render_template, request

from app.features.explore import explore_bp
from app.features.explore.forms import ExploreForm
from app.features.explore.services import ExploreService
from app.features.metrics.services import DatasetCounterService

explore_service = ExploreService()
dataset_counter_service = DatasetCounterService()


@explore_bp.route("/explore", methods=["GET"])
def index():
    return render_template(
        "explore/index.html",
        form=ExploreForm(),
        query=request.args.get("query", ""),
        author=request.args.get("author", ""),
        start_date=request.args.get("start_date", ""),
        end_date=request.args.get("end_date", ""),
    )


@explore_bp.route("/explore", methods=["POST"])
def search():
    datasets = explore_service.filter(**(request.get_json(silent=True) or {}))
    # One pair of queries for the whole page, not two per result.
    counts = dataset_counter_service.counts_for_many(dataset.id for dataset in datasets)
    return jsonify([{**dataset.to_dict(), "counts": counts[dataset.id]} for dataset in datasets])
