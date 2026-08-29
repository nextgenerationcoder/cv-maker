"""Symmetric encryption for API keys at rest, keyed off JWT_SECRET (the
one secret this app already requires you to set). Not a substitute for a
real secrets manager, but keeps a personal API key out of plaintext in
the SQLite file — appropriate for this app's size and threat model.
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


def _fernet() -> Fernet:
    secret = os.environ.get("JWT_SECRET", "dev-secret-change-me").encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret).digest())
    return Fernet(key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise ValueError("Stored API key could not be decrypted (JWT_SECRET may have changed).")
