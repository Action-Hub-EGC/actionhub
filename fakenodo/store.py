from __future__ import annotations

import copy
import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable


class DepositionStore:
    """Persistent SQLite store for Fakenodo depositions."""

    VALID_STATES = {"unsubmitted", "done"}

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS depositions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conceptrecid INTEGER,
                    doi TEXT,
                    state TEXT NOT NULL CHECK (state IN ('unsubmitted', 'done')),
                    metadata TEXT NOT NULL,
                    files TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                )
                """
            )

    @staticmethod
    def _row_to_deposition(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "conceptrecid": row["conceptrecid"],
            "doi": row["doi"],
            "state": row["state"],
            "metadata": json.loads(row["metadata"]),
            "files": json.loads(row["files"]),
            "version": row["version"],
        }

    def create(
        self,
        deposition_id: int | None = None,
        *,
        conceptrecid: int | None = None,
        doi: str | None = None,
        state: str = "unsubmitted",
        metadata: dict[str, Any] | None = None,
        files: Iterable[Any] | None = None,
        version: int = 1,
    ) -> dict[str, Any]:
        if state not in self.VALID_STATES:
            raise ValueError("state must be 'unsubmitted' or 'done'")

        metadata_value = copy.deepcopy(metadata or {})
        files_value = copy.deepcopy(list(files or []))

        with self._lock, self._connect() as connection:
            if deposition_id is None:
                cursor = connection.execute(
                    """
                    INSERT INTO depositions
                        (doi, state, metadata, files, version)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        doi,
                        state,
                        json.dumps(metadata_value, ensure_ascii=False),
                        json.dumps(files_value, ensure_ascii=False),
                        version,
                    ),
                )
                deposition_id = cursor.lastrowid
                connection.execute(
                    "UPDATE depositions SET conceptrecid = ? WHERE id = ?",
                    (conceptrecid or deposition_id, deposition_id),
                )
            else:
                connection.execute(
                    """
                    INSERT INTO depositions
                        (id, conceptrecid, doi, state, metadata, files, version)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        deposition_id,
                        conceptrecid if conceptrecid is not None else deposition_id,
                        doi,
                        state,
                        json.dumps(metadata_value, ensure_ascii=False),
                        json.dumps(files_value, ensure_ascii=False),
                        version,
                    ),
                )

        return self.get(deposition_id)

    def get(self, deposition_id: int) -> dict[str, Any] | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM depositions WHERE id = ?", (deposition_id,)
            ).fetchone()
        return self._row_to_deposition(row) if row else None

    def get_by_id(self, deposition_id: int) -> dict[str, Any] | None:
        return self.get(deposition_id)

    def list(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM depositions ORDER BY id"
            ).fetchall()
        return [self._row_to_deposition(row) for row in rows]

    def all(self) -> list[dict[str, Any]]:
        return self.list()

    def update(self, deposition_id: int, **changes: Any) -> dict[str, Any] | None:
        allowed = {
            "conceptrecid": "conceptrecid",
            "doi": "doi",
            "state": "state",
            "metadata": "metadata",
            "files": "files",
            "version": "version",
        }
        if not changes:
            return self.get(deposition_id)

        unknown = set(changes) - set(allowed)
        if unknown:
            raise ValueError(f"unsupported deposition fields: {', '.join(sorted(unknown))}")

        if "state" in changes and changes["state"] not in self.VALID_STATES:
            raise ValueError("state must be 'unsubmitted' or 'done'")

        assignments: list[str] = []
        values: list[Any] = []
        for field, column in allowed.items():
            if field not in changes:
                continue
            value = changes[field]
            if field in {"metadata", "files"}:
                value = json.dumps(copy.deepcopy(value), ensure_ascii=False)
            assignments.append(f"{column} = ?")
            values.append(value)

        values.append(deposition_id)
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE depositions SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
            if cursor.rowcount == 0:
                return None
        return self.get(deposition_id)

    def delete(self, deposition_id: int) -> bool:
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM depositions WHERE id = ?", (deposition_id,)
            )
            return cursor.rowcount > 0


SQLiteDepositionStore = DepositionStore
