"""SQLite storage, migrations and small repository helpers.

The project intentionally uses the Python standard library only: sqlite3 ships
with CPython, needs no server and keeps the supply chain at zero runtime
packages.  Each thread gets its own connection (WAL mode), which is the correct
model for ThreadingHTTPServer plus the simulation worker.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .config import ROOT, settings

_LOCAL = threading.local()
_LOCK = threading.RLock()
_MIGRATIONS = ROOT / "app" / "migrations"


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def json_loads(value: str | None, default: Any = None) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def connect() -> sqlite3.Connection:
    conn = getattr(_LOCAL, "conn", None)
    if conn is not None and getattr(_LOCAL, "path", None) == str(settings.db_path):
        return conn
    path = Path(settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=15000")
    conn.execute("PRAGMA foreign_keys=ON")
    _LOCAL.conn = conn
    _LOCAL.path = str(path)
    return conn


def close_thread_connection() -> None:
    conn = getattr(_LOCAL, "conn", None)
    if conn is not None:
        conn.close()
        _LOCAL.conn = None


def _applied(conn: sqlite3.Connection) -> set[str]:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    return {row["name"] for row in conn.execute("SELECT name FROM schema_migrations")}


def migrate() -> list[str]:
    """Apply every migration file once, in name order."""
    applied: list[str] = []
    conn = connect()
    with _LOCK:
        done = _applied(conn)
        for path in sorted(_MIGRATIONS.glob("*.sql")):
            if path.name in done:
                continue
            sql = path.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT INTO schema_migrations(name, applied_at) VALUES (?, ?)",
                (path.name, datetime.utcnow().isoformat() + "Z"),
            )
            applied.append(path.name)
    return applied


def query(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return list(connect().execute(sql, tuple(params)))


def query_one(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return connect().execute(sql, tuple(params)).fetchone()


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    with _LOCK:
        cur = connect().execute(sql, tuple(params))
        return cur.lastrowid or cur.rowcount


def executemany(sql: str, rows: Iterable[Iterable[Any]]) -> int:
    with _LOCK:
        cur = connect().executemany(sql, rows)
        return cur.rowcount


def transaction() -> Any:
    return _Transaction()


class _Transaction:
    def __enter__(self) -> sqlite3.Connection:
        self.conn = connect()
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if exc_type is None:
            self.conn.execute("COMMIT")
        else:
            self.conn.execute("ROLLBACK")
        return False


def get_meta(key: str, default: str | None = None) -> str | None:
    row = query_one("SELECT value FROM meta WHERE key = ?", (key,))
    return row["value"] if row else default


def set_meta(key: str, value: str) -> None:
    execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def table_count(table: str) -> int:
    allowed = {
        "flights",
        "screens",
        "outlets",
        "airlines",
        "campaigns",
        "creatives",
        "impressions",
        "redemptions",
        "decisions",
        "incidents",
        "daily_stats",
        "segment_stats",
        "promos",
        "zones",
        "gates",
        "advertisers",
        "packages",
        "marketplace",
    }
    if table not in allowed:
        raise ValueError(f"unsupported table count: {table}")
    row = query_one(f"SELECT COUNT(*) AS c FROM {table}")
    return int(row["c"]) if row else 0


def reset_database() -> None:
    """Remove the database file and all WAL companions (seed/tests only)."""
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(settings.db_path) + suffix)
        if path.exists():
            try:
                path.unlink()
            except PermissionError:
                pass
    close_thread_connection()