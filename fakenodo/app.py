import os

from flask import Blueprint, Flask, jsonify, request
from werkzeug.exceptions import BadRequest

from fakenodo.store import DepositionStore


def create_app(store: DepositionStore | None = None) -> Flask:
    app = Flask(__name__)
    app_store = store or DepositionStore(os.getenv("FAKENODO_STORE_PATH", "./data/fakenodo.sqlite3"))
    depositions = Blueprint(
        "depositions",
        __name__,
        url_prefix="/api/deposit/depositions",
    )

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @depositions.post("")
    def create_deposition():
        raw_body = request.get_data(cache=True)
        if not raw_body.strip():
            payload = {}
        elif not request.is_json:
            return jsonify({"message": "Content-Type must be application/json"}), 415
        else:
            try:
                payload = request.get_json(silent=False)
            except BadRequest:
                return jsonify({"message": "Malformed JSON"}), 400

        if not isinstance(payload, dict):
            return jsonify({"message": "The request body must be a JSON object"}), 400

        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            return jsonify({"message": "metadata must be a JSON object"}), 400

        deposition = app_store.create(metadata=metadata or {})
        return jsonify(deposition), 201

    @depositions.get("")
    def list_depositions():
        return jsonify(app_store.list()), 200

    @depositions.get("/<int:deposition_id>")
    def get_deposition(deposition_id: int):
        deposition = app_store.get(deposition_id)
        if deposition is None:
            return jsonify({"message": "Deposition not found"}), 404
        return jsonify(deposition), 200

    @depositions.delete("/<int:deposition_id>")
    def delete_deposition(deposition_id: int):
        if not app_store.delete(deposition_id):
            return jsonify({"message": "Deposition not found"}), 404
        return "", 204

    app.register_blueprint(depositions)

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"message": "Not found"}), 404

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
