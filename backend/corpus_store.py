"""Tracks background 'word-frequency corpus' collection runs (see
corpus_collector.py) - a long-running job (potentially 20+ minutes to
reach a large word target), so it runs in a background thread and this
store is how the API reports progress instead of blocking the request.

Follows the same sqlite pattern as tailoring_store.py/settings_store.py.
"""
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

DB_PATH = os.environ.get("CV_DB_PATH", "cv_profiles.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS corpus_runs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            target_words INTEGER NOT NULL,
            collected_words INTEGER NOT NULL DEFAULT 0,
            posting_count INTEGER NOT NULL DEFAULT 0,
            current_step TEXT,
            error TEXT,
            output_path TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    _connect().close()


def create_run(user_id: str, target_words: int, output_path: str) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid.uuid4())
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO corpus_runs (id, user_id, status, target_words, output_path, created_at, updated_at)
            VALUES (?, ?, 'running', ?, ?, ?, ?)
            """,
            (run_id, user_id, target_words, output_path, now, now),
        )
    return get_run(run_id)


def get_run(run_id: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM corpus_runs WHERE id = ?", (run_id,)).fetchone()
    return dict(row) if row else None


def list_runs(user_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM corpus_runs WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def update_progress(run_id: str, *, collected_words: int, posting_count: int, current_step: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE corpus_runs
            SET collected_words = ?, posting_count = ?, current_step = ?, updated_at = ?
            WHERE id = ?
            """,
            (collected_words, posting_count, current_step, now, run_id),
        )


def mark_done(run_id: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE corpus_runs SET status = 'done', current_step = 'done', updated_at = ? WHERE id = ?",
            (now, run_id),
        )


def mark_failed(run_id: str, error: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE corpus_runs SET status = 'failed', error = ?, updated_at = ? WHERE id = ?",
            (error, now, run_id),
        )
