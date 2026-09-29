from __future__ import annotations

from pathlib import Path
import sqlite3


class BrowserSessionStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS browser_sessions (
                    id TEXT PRIMARY KEY,
                    csrf TEXT NOT NULL,
                    expires REAL NOT NULL
                )
                """
            )

    def put(self, session_id: str, csrf: str, expires: float) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO browser_sessions (id, csrf, expires)
                VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET csrf = excluded.csrf, expires = excluded.expires
                """,
                (session_id, csrf, float(expires)),
            )

    def get(self, session_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT csrf, expires FROM browser_sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row is None:
                return None
            expires = float(row["expires"])
            if expires < _now():
                connection.execute("DELETE FROM browser_sessions WHERE id = ?", (session_id,))
                return None
            return {"csrf": row["csrf"], "expires": expires}

    def delete(self, session_id: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM browser_sessions WHERE id = ?", (session_id,))

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM browser_sessions")

    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 5000")
        return _ClosingConnection(connection)


class _ClosingConnection:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def __enter__(self) -> sqlite3.Connection:
        return self.connection

    def __exit__(self, exc_type, exc, traceback) -> None:
        try:
            if exc_type is None:
                self.connection.commit()
            else:
                self.connection.rollback()
        finally:
            self.connection.close()


def _now() -> float:
    import time

    return time.time()
