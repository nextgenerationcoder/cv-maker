import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from cv_models import CVProfile

DB_PATH = os.environ.get("CV_DB_PATH", "cv_profiles.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cv_profiles (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            uploaded_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            data TEXT NOT NULL
        )
        """
    )
    try:
        conn.execute("ALTER TABLE cv_profiles ADD COLUMN updated_at TEXT")
        conn.execute("UPDATE cv_profiles SET updated_at = uploaded_at WHERE updated_at IS NULL")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # column already exists — fine on every run after the first
    return conn


def init_db() -> None:
    _connect().close()


def save_cv(cv_id: str, filename: str, profile: CVProfile) -> str:
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO cv_profiles (id, filename, uploaded_at, updated_at, data) VALUES (?, ?, ?, ?, ?)",
            (cv_id, filename, now, now, profile.model_dump_json()),
        )
        conn.commit()
    finally:
        conn.close()
    return now


def update_cv(cv_id: str, profile: CVProfile, filename: Optional[str] = None) -> Optional[str]:
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        if filename is not None:
            cur = conn.execute(
                "UPDATE cv_profiles SET data = ?, filename = ?, updated_at = ? WHERE id = ?",
                (profile.model_dump_json(), filename, now, cv_id),
            )
        else:
            cur = conn.execute(
                "UPDATE cv_profiles SET data = ?, updated_at = ? WHERE id = ?",
                (profile.model_dump_json(), now, cv_id),
            )
        conn.commit()
        updated = cur.rowcount > 0
    finally:
        conn.close()
    return now if updated else None


def fetch_cv(cv_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, filename, uploaded_at, updated_at, data FROM cv_profiles WHERE id = ?",
            (cv_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "id": row[0],
        "filename": row[1],
        "uploaded_at": row[2],
        "updated_at": row[3],
        "profile": json.loads(row[4]),
    }


def list_cvs(limit: int = 20) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, filename, uploaded_at, updated_at FROM cv_profiles ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [
        {"id": r[0], "filename": r[1], "uploaded_at": r[2], "updated_at": r[3]} for r in rows
    ]
