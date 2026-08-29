import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional

import crypto_util

DB_PATH = os.environ.get("CV_DB_PATH", "cv_profiles.db")

VALID_PROVIDERS = {"anthropic", "deepseek"}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY,
            llm_provider TEXT NOT NULL DEFAULT 'anthropic',
            llm_api_key_enc TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    return conn


def init_db() -> None:
    _connect().close()


def get_settings(user_id: str) -> Optional[dict]:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT llm_provider, llm_api_key_enc, updated_at FROM user_settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {"llm_provider": row[0], "llm_api_key_enc": row[1], "updated_at": row[2]}


def get_decrypted_api_key(user_id: str) -> Optional[str]:
    settings = get_settings(user_id)
    if settings is None or not settings["llm_api_key_enc"]:
        return None
    return crypto_util.decrypt(settings["llm_api_key_enc"])


def upsert_settings(user_id: str, llm_provider: str, api_key: Optional[str] = None) -> dict:
    """api_key: None = leave unchanged, "" = clear it, otherwise store (encrypted)."""
    if llm_provider not in VALID_PROVIDERS:
        raise ValueError(f"Unknown provider: {llm_provider}")
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    try:
        existing = conn.execute(
            "SELECT llm_api_key_enc FROM user_settings WHERE user_id = ?", (user_id,)
        ).fetchone()
        if api_key is None:
            api_key_enc = existing[0] if existing else None
        elif api_key == "":
            api_key_enc = None
        else:
            api_key_enc = crypto_util.encrypt(api_key)

        conn.execute(
            "INSERT INTO user_settings (user_id, llm_provider, llm_api_key_enc, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET llm_provider = excluded.llm_provider, "
            "llm_api_key_enc = excluded.llm_api_key_enc, updated_at = excluded.updated_at",
            (user_id, llm_provider, api_key_enc, now),
        )
        conn.commit()
    finally:
        conn.close()
    return get_settings(user_id)
