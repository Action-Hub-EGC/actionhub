import hashlib
import os

from flask import Blueprint, Flask, jsonify, request, url_for
from werkzeug.exceptions import BadRequest

from fakenodo.store import DepositionError, DepositionStore


def _json_object_body():
    """Parse the request body as a JSON object.

    Returns ``(payload, None)`` or ``(None, error_response)``. An empty body is
    an empty object.
    """
    raw_body = request.get_data(cache=True)
    if not raw_body.strip():
        return {}, None
    if not request.is_json:
        return None, (jsonify({"message": "Content-Type must be application/json"}), 415)
    try:
        payload = request.get_json(silent=False)
    except BadRequest:
        return None, (jsonify({"message": "Malformed JSON"}), 400)
    if not isinstance(payload, dict):
        return None, (jsonify({"message": "The request body must be a JSON object"}), 400)
    return payload, None


def _not_found():
    return jsonify({"message": "Deposition not found"}), 404


def create_app(store: DepositionStore | None = None) -> Flask:
    app = Flask(__name__)
    app_store = store or DepositionStore(os.getenv("FAKENODO_STORE_PATH", "./data/fakenodo.sqlite3"))
    app.extensions["fakenodo_store"] = app_store
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
        payload, error = _json_object_body()
        if error:
            return error

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
            return _not_found()
        return jsonify(deposition), 200

    @depositions.put("/<int:deposition_id>")
    def update_deposition(deposition_id: int):
        payload, error = _json_object_body()
        if error:
            return error

        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            return jsonify({"message": "metadata must be a JSON object"}), 400

        # Only the metadata changes: the DOI, the state and the files stay.
        deposition = app_store.update(deposition_id, metadata=metadata)
        if deposition is None:
            return _not_found()
        return jsonify(deposition), 200

    @depositions.post("/<int:deposition_id>/files")
    def upload_file(deposition_id: int):
        deposition = app_store.get(deposition_id)
        if deposition is None:
            return _not_found()
        if deposition["state"] == "done":
            return jsonify({"message": "Cannot upload files to a published deposition"}), 400

        uploaded_file = request.files.get("file")
        if uploaded_file is None:
            return jsonify({"message": "file is required"}), 400

        filename = request.form.get("name") or uploaded_file.filename
        if not filename:
            return jsonify({"message": "file name is required"}), 400

        digest = hashlib.md5()
        size = 0
        while chunk := uploaded_file.stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)

        file_data = {
            # max + 1, not len + 1: after a delete, len + 1 could repeat an id.
            "id": max((file["id"] for file in deposition["files"]), default=0) + 1,
            "filename": filename,
            "filesize": size,
            "checksum": f"md5:{digest.hexdigest()}",
        }
        app_store.update(deposition_id, files=[*deposition["files"], file_data])
        return jsonify(file_data), 201

    @depositions.delete("/<int:deposition_id>/files/<int:file_id>")
    def delete_file(deposition_id: int, file_id: int):
        deposition = app_store.get(deposition_id)
        if deposition is None:
            return _not_found()
        if deposition["state"] == "done":
            return jsonify({"message": "Cannot delete files from a published deposition"}), 400

        files = [file for file in deposition["files"] if file["id"] != file_id]
        if len(files) == len(deposition["files"]):
            return jsonify({"message": "File not found"}), 404
        app_store.update(deposition_id, files=files)
        return "", 204

    @depositions.post("/<int:deposition_id>/actions/publish")
    def publish_deposition(deposition_id: int):
        try:
            deposition = app_store.publish(deposition_id)
        except DepositionError as error:
            return jsonify({"message": str(error)}), 400
        if deposition is None:
            return _not_found()
        return jsonify(deposition), 202

    @depositions.post("/<int:deposition_id>/actions/newversion")
    def new_version(deposition_id: int):
        try:
            result = app_store.new_version(deposition_id)
        except DepositionError as error:
            return jsonify({"message": str(error)}), 400
        if result is None:
            return _not_found()

        # As Zenodo does, the response is the deposition the action was called
        # on, and the new draft is reached through links.latest_draft.
        source, draft = result
        latest_draft = url_for("depositions.get_deposition", deposition_id=draft["id"], _external=True)
        return jsonify({**source, "links": {"latest_draft": latest_draft}}), 201

    @depositions.delete("/<int:deposition_id>")
    def delete_deposition(deposition_id: int):
        if not app_store.delete(deposition_id):
            return _not_found()
        return "", 204

    app.register_blueprint(depositions)

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"message": "Not found"}), 404

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
