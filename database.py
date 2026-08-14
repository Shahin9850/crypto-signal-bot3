"""
Very small SQLite wrapper for persisting signals and their outcomes.

Table `signals`:
    id            INTEGER PRIMARY KEY
    symbol        TEXT
    direction     TEXT      ('long' / 'short')
    entry_price   REAL
    stop_loss     REAL
    take_profit   REAL
    status        TEXT      ('open' / 'tp' / 'sl')
    created_at    TEXT      (ISO timestamp, UTC)
    closed_at     TEXT      (ISO timestamp, UTC, nullable)
    notified_batch INTEGER  (0/1, whether this signal was already counted in a batch report)
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    entry_price REAL NOT NULL,
    stop_loss REAL NOT NULL,
    take_profit REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL,
    closed_at TEXT,
    notified_batch INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def insert_signal(symbol, direction, entry_price, stop_loss, take_profit) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO signals
               (symbol, direction, entry_price, stop_loss, take_profit, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'open', ?)""",
            (
                symbol,
                direction,
                entry_price,
                stop_loss,
                take_profit,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        return cur.lastrowid


def get_open_signals():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM signals WHERE status = 'open'").fetchall()
        return [dict(r) for r in rows]


def close_signal(signal_id: int, status: str):
    """status must be 'tp' or 'sl'"""
    assert status in ("tp", "sl")
    with get_conn() as conn:
        conn.execute(
            "UPDATE signals SET status = ?, closed_at = ? WHERE id = ?",
            (status, datetime.now(timezone.utc).isoformat(), signal_id),
        )


def get_all_signals(limit: int = None):
    with get_conn() as conn:
        q = "SELECT * FROM signals ORDER BY id DESC"
        if limit:
            q += f" LIMIT {int(limit)}"
        rows = conn.execute(q).fetchall()
        return [dict(r) for r in rows]


def count_total_signals() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) as c FROM signals").fetchone()
        return row["c"]


def get_unbatched_signals(batch_size: int):
    """Return the oldest `batch_size` signals that have not yet been included
    in an automatic batch report (regardless of open/closed status)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM signals WHERE notified_batch = 0 ORDER BY id ASC LIMIT ?",
            (batch_size,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_batch_notified(ids):
    if not ids:
        return
    with get_conn() as conn:
        conn.executemany(
            "UPDATE signals SET notified_batch = 1 WHERE id = ?",
            [(i,) for i in ids],
        )


def has_open_signal_for_symbol(symbol: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as c FROM signals WHERE symbol = ? AND status = 'open'",
            (symbol,),
        ).fetchone()
        return row["c"] > 0


def get_meta(key: str):
    """Small key/value store, used e.g. to remember the last processed
    Telegram update id between separate script runs (GitHub Actions cron)."""
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def set_meta(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
