"""SQLite-backed working store for the per-symbol data lakes.

Why this exists
---------------
A lake is one JSON document keyed by symbol, so persisting a single symbol
means re-serialising the whole file. Coalescing writes made that linear rather
than quadratic, but reading one symbol still costs a full parse of a file that
reaches 155 MB.

Why JSON stays
--------------
JSON remains the interchange format, not a legacy detail:

* ``scripts/merge_shards.py`` reads and writes the lakes as JSON.
* The GitHub Actions crawlers ``git add`` the ``.json`` files by path. If those
  paths stopped being produced, ``git commit`` would fall through to its
  ``|| echo "No changes to commit"`` branch and a full crawl would be discarded
  with the workflow still green.
* The Colab notebooks read the ``.json`` files directly.

So SQLite is the working store and JSON is what leaves the machine. Nothing
downstream changes.

Why the database is local-only
------------------------------
``GOOGLE_DRIVE_DATA_DIR`` points at a cloud-sync folder. Sync clients copy
whole files on their own schedule and do not honour file locking, so they can
upload a database mid-transaction or restore a stale ``.db`` over a live
``-wal``. SQLite's durability assumes neither happens. A truncated JSON file
loses its tail and can still be salvaged; a corrupted database page can render
the whole file unopenable. ``_resolve_db_path`` therefore refuses to place the
database inside the Drive directory.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from typing import Any, Dict, Iterable, Optional, Tuple

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lake_records (
    lake       TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    payload    TEXT NOT NULL,
    updated_at REAL NOT NULL,
    PRIMARY KEY (lake, symbol)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_lake_records_lake ON lake_records(lake);

CREATE TABLE IF NOT EXISTS lake_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _local_data_dir() -> str:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "data")
    os.makedirs(path, exist_ok=True)
    return path


def _resolve_db_path(explicit: Optional[str] = None) -> str:
    """Returns the database path, never inside the cloud-sync directory."""
    candidate = explicit or os.environ.get("DATA_LAKE_DB_PATH", "").strip()
    if not candidate:
        candidate = os.path.join(_local_data_dir(), "lake.db")
    candidate = os.path.abspath(candidate)

    gdrive = os.environ.get("GOOGLE_DRIVE_DATA_DIR", "").strip()
    if gdrive and os.path.isdir(gdrive):
        gdrive_abs = os.path.abspath(gdrive)
        try:
            inside = os.path.commonpath([candidate, gdrive_abs]) == gdrive_abs
        except ValueError:  # different drives on Windows
            inside = False
        if inside:
            fallback = os.path.join(_local_data_dir(), os.path.basename(candidate))
            logger.warning(
                "Refusing to open the lake database inside the cloud-sync directory "
                "(%s); sync clients corrupt SQLite files. Using %s instead.",
                gdrive_abs, fallback,
            )
            return fallback
    return candidate


class SQLiteLakeStore:
    """Per-symbol store with O(1) reads and writes.

    Connections are thread-local: sqlite3 objects are not safe to share across
    threads, and this is read and written from several thread pools.
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = _resolve_db_path(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._local = threading.local()
        self._init_lock = threading.Lock()
        with self._init_lock:
            conn = self._connect()
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT INTO lake_meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            # WAL lets readers proceed during a write; NORMAL is the standard
            # durability/throughput trade-off alongside it.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn = conn
        return conn

    # --- writes ---------------------------------------------------------

    def put(self, lake: str, symbol: str, record: Any) -> None:
        """Upserts one symbol. Cost does not depend on the size of the lake."""
        symbol = str(symbol).upper().strip()
        if not symbol:
            return
        conn = self._connect()
        with conn:
            conn.execute(
                "INSERT INTO lake_records(lake, symbol, payload, updated_at) "
                "VALUES(?,?,?,?) ON CONFLICT(lake, symbol) DO UPDATE SET "
                "payload=excluded.payload, updated_at=excluded.updated_at",
                (lake, symbol, json.dumps(record, ensure_ascii=False), time.time()),
            )

    def put_many(self, lake: str, records: Dict[str, Any]) -> int:
        """Upserts many symbols in one transaction."""
        now = time.time()
        rows = [
            (lake, str(s).upper().strip(), json.dumps(r, ensure_ascii=False), now)
            for s, r in records.items()
            if str(s).strip()
        ]
        if not rows:
            return 0
        conn = self._connect()
        with conn:
            conn.executemany(
                "INSERT INTO lake_records(lake, symbol, payload, updated_at) "
                "VALUES(?,?,?,?) ON CONFLICT(lake, symbol) DO UPDATE SET "
                "payload=excluded.payload, updated_at=excluded.updated_at",
                rows,
            )
        return len(rows)

    def delete(self, lake: str, symbol: str) -> None:
        conn = self._connect()
        with conn:
            conn.execute(
                "DELETE FROM lake_records WHERE lake=? AND symbol=?",
                (lake, str(symbol).upper().strip()),
            )

    # --- reads ----------------------------------------------------------

    def get(self, lake: str, symbol: str) -> Optional[Any]:
        """Reads one symbol without parsing the rest of the lake."""
        row = self._connect().execute(
            "SELECT payload FROM lake_records WHERE lake=? AND symbol=?",
            (lake, str(symbol).upper().strip()),
        ).fetchone()
        return json.loads(row[0]) if row else None

    def get_all(self, lake: str) -> Dict[str, Any]:
        """Reads a whole lake, matching the shape the JSON file had."""
        cur = self._connect().execute(
            "SELECT symbol, payload FROM lake_records WHERE lake=?", (lake,)
        )
        return {symbol: json.loads(payload) for symbol, payload in cur}

    def symbols(self, lake: str) -> Iterable[str]:
        cur = self._connect().execute(
            "SELECT symbol FROM lake_records WHERE lake=? ORDER BY symbol", (lake,)
        )
        return [r[0] for r in cur]

    def count(self, lake: str) -> int:
        return self._connect().execute(
            "SELECT COUNT(*) FROM lake_records WHERE lake=?", (lake,)
        ).fetchone()[0]

    def lakes(self) -> Iterable[str]:
        return [
            r[0] for r in self._connect().execute(
                "SELECT DISTINCT lake FROM lake_records ORDER BY lake"
            )
        ]

    # --- JSON interchange ----------------------------------------------

    def import_json(self, lake: str, json_path: str) -> int:
        """Seeds a lake from its existing JSON file. Returns rows written."""
        with open(json_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            raise ValueError(f"{json_path} is not a symbol-keyed object")
        return self.put_many(lake, data)

    def export_json(self, lake: str, json_path: str, indent: Optional[int] = None) -> int:
        """Writes the lake back out as the JSON file downstream tools expect.

        Atomic: the temp file is replaced into place, so a reader never sees a
        half-written lake.
        """
        data = self.get_all(lake)
        os.makedirs(os.path.dirname(os.path.abspath(json_path)) or ".", exist_ok=True)
        tmp = f"{json_path}.tmp_{os.getpid()}_{int(time.time() * 1000)}"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=indent)
        os.replace(tmp, json_path)
        return len(data)

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
