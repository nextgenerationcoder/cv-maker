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
            data TEXT NOT NULL
        )
        """
    )
    return conn


def init_db() -> None:
    _connect().close()


def save_cv(cv_id: str, filename: str, profile: CVProfile) -> str:
    uploaded_at = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO cv_profiles (id, filename, uploaded_at, data) VALUES (?, ?, ?, ?)",
            (cv_id, filename, uploaded_at, profile.model_dump_json()),
        )
        conn.commit()
    finally:
        conn.close()
    return uploaded_at


def fetch_cv(cv_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, filename, uploaded_at, data FROM cv_profiles WHERE id = ?",
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
        "profile": json.loads(row[3]),
    }


def list_cvs(limit: int = 20) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, filename, uploaded_at FROM cv_profiles ORDER BY uploaded_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()
    return [{"id": r[0], "filename": r[1], "uploaded_at": r[2]} for r in rows]
