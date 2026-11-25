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


class DepositionError(ValueError):
    """Raised when an action is not allowed in the deposition's current state."""


class PublishError(DepositionError):
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

    def list_versions(self, conceptrecid: int) -> list[dict[str, Any]]:
        """Return every deposition of a concept, oldest version first."""
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM depositions WHERE conceptrecid = ? ORDER BY version, id",
                (conceptrecid,),
            ).fetchall()
        return [self._row_to_deposition(row) for row in rows]

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
                # Column names come from the ``allowed`` whitelist; values are bound.
                f"UPDATE depositions SET {', '.join(assignments)} WHERE id = ?",  # nosec B608
                values,
            )
            if cursor.rowcount == 0:
                return None
        return self.get(deposition_id)

    def publish(self, deposition_id: int) -> dict[str, Any] | None:
        """Move a deposition to ``done`` and assign it a fake DOI.

        The DOI is ``10.5072/fakenodo.<id>``, unique because the id is. The
        concept DOI is set only on the first publish of the concept; later
        versions inherit it. Returns ``None`` if the deposition does not exist
        and raises ``PublishError`` if it is already published, has no files
        or, as Zenodo does, has the same files as a published version of its
        concept. The check and the update share the store lock, so two
        concurrent publishes cannot both succeed.
        """
        with self._lock:
            deposition = self.get(deposition_id)
            if deposition is None:
                return None
            if deposition["state"] == "done":
                raise PublishError("Deposition is already published")
            if not deposition["files"]:
                raise PublishError("Minimum one file must be provided.")

            content = self._files_content(deposition["files"])
            for other in self.list_versions(deposition["conceptrecid"]):
                if other["state"] == "done" and self._files_content(other["files"]) == content:
                    raise PublishError("New version's files must differ from all previous versions.")

            changes: dict[str, Any] = {
                "state": "done",
                "doi": f"{DOI_PREFIX}/fakenodo.{deposition_id}",
            }
            if not deposition["conceptdoi"]:
                changes["conceptdoi"] = f"{DOI_PREFIX}/fakenodo.concept.{deposition['conceptrecid']}"
            return self.update(deposition_id, **changes)

    @staticmethod
    def _files_content(files: list[dict[str, Any]]) -> list[str]:
        """What identifies a set of files: their checksums, ignoring order."""
        return sorted(str(file.get("checksum") or file.get("filename")) for file in files)

    def new_version(self, deposition_id: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Create a draft for the next version of a published deposition.

        The draft shares ``conceptrecid`` and ``conceptdoi``, has no DOI until
        it is published and starts with the metadata and files of the latest
        published version, so newversion on an old version still builds on the
        newest one. A concept has at most one draft: if it already exists, it
        is returned instead of creating another. Returns ``(source, draft)``,
        or ``None`` if the deposition does not exist, and raises
        ``DepositionError`` if it is not published.
        """
        with self._lock:
            source = self.get(deposition_id)
            if source is None:
                return None
            if source["state"] != "done":
                raise DepositionError("Only published depositions can have a new version")

            versions = self.list_versions(source["conceptrecid"])
            draft = next((version for version in versions if version["state"] == "unsubmitted"), None)
            if draft is None:
                latest = [version for version in versions if version["state"] == "done"][-1]
                draft = self.create(
                    conceptrecid=source["conceptrecid"],
                    conceptdoi=source["conceptdoi"],
                    metadata=latest["metadata"],
                    files=latest["files"],
                    version=max(version["version"] for version in versions) + 1,
                )
            return source, draft

    def delete(self, deposition_id: int) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute("DELETE FROM depositions WHERE id = ?", (deposition_id,))
            return cursor.rowcount > 0


SQLiteDepositionStore = DepositionStore
