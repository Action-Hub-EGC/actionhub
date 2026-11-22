from __future__ import annotations

import copy
import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

# DataCite test prefix: DOIs under it never resolve in doi.org.
DOI_PREFIX = "10.5072"


class PublishError(ValueError):
    """Raised when a deposition cannot be published."""


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

    @contextmanager
    def _connection(self):
        """Open one connection, commit/rollback and close it reliably."""
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._lock, self._connection() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS depositions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conceptrecid INTEGER,
                    conceptdoi TEXT,
                    doi TEXT,
                    state TEXT NOT NULL CHECK (state IN ('unsubmitted', 'done')),
                    metadata TEXT NOT NULL,
                    files TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                )
                """)
            # Stores created before the concept DOI existed lack the column.
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(depositions)")}
            if "conceptdoi" not in columns:
                connection.execute("ALTER TABLE depositions ADD COLUMN conceptdoi TEXT")

    @staticmethod
    def _row_to_deposition(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "conceptrecid": row["conceptrecid"],
            "conceptdoi": row["conceptdoi"],
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
        conceptdoi: str | None = None,
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

        with self._lock, self._connection() as connection:
            if deposition_id is None:
                cursor = connection.execute(
                    """
                    INSERT INTO depositions
                        (conceptdoi, doi, state, metadata, files, version)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        conceptdoi,
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
                        (id, conceptrecid, conceptdoi, doi, state, metadata, files, version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        deposition_id,
                        conceptrecid if conceptrecid is not None else deposition_id,
                        conceptdoi,
                        doi,
                        state,
                        json.dumps(metadata_value, ensure_ascii=False),
                        json.dumps(files_value, ensure_ascii=False),
                        version,
                    ),
                )

        return self.get(deposition_id)

    def get(self, deposition_id: int) -> dict[str, Any] | None:
        with self._lock, self._connection() as connection:
            row = connection.execute("SELECT * FROM depositions WHERE id = ?", (deposition_id,)).fetchone()
        return self._row_to_deposition(row) if row else None

    def get_by_id(self, deposition_id: int) -> dict[str, Any] | None:
        return self.get(deposition_id)

    def list(self) -> list[dict[str, Any]]:
        with self._lock, self._connection() as connection:
            rows = connection.execute("SELECT * FROM depositions ORDER BY id").fetchall()
        return [self._row_to_deposition(row) for row in rows]

    def all(self) -> list[dict[str, Any]]:
        return self.list()

    def update(self, deposition_id: int, **changes: Any) -> dict[str, Any] | None:
        allowed = {
            "conceptrecid": "conceptrecid",
            "conceptdoi": "conceptdoi",
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
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                f"UPDATE depositions SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
            if cursor.rowcount == 0:
                return None
        return self.get(deposition_id)

    def publish(self, deposition_id: int) -> dict[str, Any] | None:
        """Move a deposition to ``done`` and assign it a fake DOI.

        The DOI is ``10.5072/fakenodo.<id>``, unique because the id is. The
        concept DOI is set only on the first publish of the concept. Returns
        ``None`` if the deposition does not exist and raises ``PublishError``
        if it is already published or has no files, as Zenodo does. The check
        and the update share the store lock, so two concurrent publishes
        cannot both succeed.
        """
        with self._lock:
            deposition = self.get(deposition_id)
            if deposition is None:
                return None
            if deposition["state"] == "done":
                raise PublishError("Deposition is already published")
            if not deposition["files"]:
                raise PublishError("Minimum one file must be provided.")

            changes: dict[str, Any] = {
                "state": "done",
                "doi": f"{DOI_PREFIX}/fakenodo.{deposition_id}",
            }
            if not deposition["conceptdoi"]:
                changes["conceptdoi"] = f"{DOI_PREFIX}/fakenodo.concept.{deposition['conceptrecid']}"
            return self.update(deposition_id, **changes)

    def delete(self, deposition_id: int) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute("DELETE FROM depositions WHERE id = ?", (deposition_id,))
            return cursor.rowcount > 0


SQLiteDepositionStore = DepositionStore
