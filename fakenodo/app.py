import os

from flask import Flask, jsonify, request

from fakenodo.store import DepositionStore


def create_app(store: DepositionStore | None = None) -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = False
    app_store = store or DepositionStore(
        os.getenv("FAKENODO_STORE_PATH", "./data/fakenodo.sqlite3")
    )

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.post("/")
    def create_deposition():
        payload = request.get_json(silent=True)
        if payload is not None and not isinstance(payload, dict):
            return jsonify({"message": "The request body must be a JSON object"}), 400

        payload = payload or {}
        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            return jsonify({"message": "metadata must be a JSON object"}), 400

        deposition = app_store.create(metadata=metadata or {})
        return jsonify(deposition), 201

    @app.get("/")
    def list_depositions():
        return jsonify(app_store.list()), 200

    @app.get("/<int:deposition_id>")
    def get_deposition(deposition_id: int):
        deposition = app_store.get(deposition_id)
        if deposition is None:
            return jsonify({"message": "Deposition not found"}), 404
        return jsonify(deposition), 200

    @app.delete("/<int:deposition_id>")
    def delete_deposition(deposition_id: int):
        if not app_store.delete(deposition_id):
            return jsonify({"message": "Deposition not found"}), 404
        return "", 204

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"message": "Not found"}), 404

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
