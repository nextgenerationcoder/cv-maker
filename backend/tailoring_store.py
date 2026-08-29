import json
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
        CREATE TABLE IF NOT EXISTS tailoring_jobs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            cv_id TEXT NOT NULL,
            title TEXT NOT NULL,
            company TEXT,
            location TEXT,
            description TEXT,
            job_url TEXT,
            job_type TEXT,
            job_analysis TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS resume_matches (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            cv_id TEXT NOT NULL,
            match_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(job_id, cv_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tailored_cvs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            job_id TEXT NOT NULL,
            cv_id TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            cv_json TEXT NOT NULL,
            selection_json TEXT NOT NULL,
            provenance_json TEXT NOT NULL,
            evaluation_json TEXT NOT NULL,
            generation_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    return conn


def init_db() -> None:
    _connect().close()


# ---------- tailoring_jobs ----------


def create_job(user_id: str, cv_id: str, job: dict) -> dict:
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO tailoring_jobs "
            "(id, user_id, cv_id, title, company, location, description, job_url, job_type, "
            "job_analysis, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                job_id,
                user_id,
                cv_id,
                job.get("title") or "Untitled role",
                job.get("company"),
                job.get("location"),
                job.get("description"),
                job.get("job_url"),
                job.get("job_type"),
                None,
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return fetch_job(job_id, user_id)


def set_job_analysis(job_id: str, user_id: str, job_analysis: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            "UPDATE tailoring_jobs SET job_analysis = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (json.dumps(job_analysis), now, job_id, user_id),
        )
        conn.commit()
    finally:
        conn.close()


def fetch_job(job_id: str, user_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, user_id, cv_id, title, company, location, description, job_url, job_type, "
            "job_analysis, created_at, updated_at FROM tailoring_jobs WHERE id = ? AND user_id = ?",
            (job_id, user_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "cv_id": row[2],
        "title": row[3],
        "company": row[4],
        "location": row[5],
        "description": row[6],
        "job_url": row[7],
        "job_type": row[8],
        "job_analysis": json.loads(row[9]) if row[9] else None,
        "created_at": row[10],
        "updated_at": row[11],
    }


def list_jobs(user_id: str, limit: int = 50) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, title, company, location, job_url, job_analysis, created_at, updated_at "
            "FROM tailoring_jobs WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "id": r[0],
            "title": r[1],
            "company": r[2],
            "location": r[3],
            "job_url": r[4],
            "has_analysis": r[5] is not None,
            "created_at": r[6],
            "updated_at": r[7],
        }
        for r in rows
    ]


def delete_job(job_id: str, user_id: str) -> bool:
    conn = _connect()
    try:
        cur = conn.execute("DELETE FROM tailoring_jobs WHERE id = ? AND user_id = ?", (job_id, user_id))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------- resume_matches ----------


def upsert_match(job_id: str, user_id: str, cv_id: str, match_json: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO resume_matches (id, job_id, user_id, cv_id, match_json, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(job_id, cv_id) DO UPDATE SET match_json = excluded.match_json, created_at = excluded.created_at",
            (str(uuid.uuid4()), job_id, user_id, cv_id, json.dumps(match_json), now),
        )
        conn.commit()
    finally:
        conn.close()


def fetch_match(job_id: str, user_id: str, cv_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT match_json, created_at FROM resume_matches WHERE job_id = ? AND user_id = ? AND cv_id = ?",
            (job_id, user_id, cv_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    match = json.loads(row[0])
    match["created_at"] = row[1]
    return match


# ---------- tailored_cvs ----------


def create_tailored_cv(
    user_id: str,
    job_id: str,
    cv_id: str,
    cv_json: dict,
    selection_json: list,
    provenance_json: list,
    evaluation_json: dict,
    generation_json: dict,
) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        version_row = conn.execute(
            "SELECT COALESCE(MAX(version_number), 0) FROM tailored_cvs WHERE job_id = ? AND user_id = ?",
            (job_id, user_id),
        ).fetchone()
        version_number = (version_row[0] or 0) + 1
        tcv_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO tailored_cvs (id, user_id, job_id, cv_id, version_number, cv_json, "
            "selection_json, provenance_json, evaluation_json, generation_json, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                tcv_id,
                user_id,
                job_id,
                cv_id,
                version_number,
                json.dumps(cv_json),
                json.dumps(selection_json),
                json.dumps(provenance_json),
                json.dumps(evaluation_json),
                json.dumps(generation_json),
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return fetch_tailored_cv(tcv_id, user_id)


def fetch_tailored_cv(tcv_id: str, user_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT id, user_id, job_id, cv_id, version_number, cv_json, selection_json, "
            "provenance_json, evaluation_json, generation_json, created_at, updated_at "
            "FROM tailored_cvs WHERE id = ? AND user_id = ?",
            (tcv_id, user_id),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return _row_to_dict(row)


def update_tailored_cv_content(tcv_id: str, user_id: str, cv_json: dict) -> Optional[dict]:
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE tailored_cvs SET cv_json = ?, updated_at = ? WHERE id = ? AND user_id = ?",
            (json.dumps(cv_json), now, tcv_id, user_id),
        )
        conn.commit()
        updated = cur.rowcount > 0
    finally:
        conn.close()
    return fetch_tailored_cv(tcv_id, user_id) if updated else None


def list_tailored_cvs_for_job(job_id: str, user_id: str) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT id, user_id, job_id, cv_id, version_number, cv_json, selection_json, "
            "provenance_json, evaluation_json, generation_json, created_at, updated_at "
            "FROM tailored_cvs WHERE job_id = ? AND user_id = ? ORDER BY version_number DESC",
            (job_id, user_id),
        ).fetchall()
    finally:
        conn.close()
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "user_id": row[1],
        "job_id": row[2],
        "cv_id": row[3],
        "version_number": row[4],
        "cv": json.loads(row[5]),
        "selection": json.loads(row[6]),
        "provenance": json.loads(row[7]),
        "evaluation": json.loads(row[8]),
        "generation": json.loads(row[9]),
        "created_at": row[10],
        "updated_at": row[11],
    }
