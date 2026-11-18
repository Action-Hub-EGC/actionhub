import os

from flask import Flask, jsonify

from fakenodo.store import DepositionStore

app = Flask(__name__)
store = DepositionStore(os.getenv("FAKENODO_STORE_PATH", "/data/fakenodo.sqlite3"))


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
