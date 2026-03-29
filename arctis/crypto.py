"""Symmetric encryption for secrets at rest (Fernet)."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet


def _fernet() -> Fernet:
    raw = os.environ.get("ARCTIS_ENCRYPTION_KEY")
    if not raw or not str(raw).strip():
        raise RuntimeError("ARCTIS_ENCRYPTION_KEY is not set or is empty")
    return Fernet(str(raw).strip().encode("ascii"))


def encrypt_key(plaintext: str) -> str:
    """Encrypt a UTF-8 string; returns ASCII-safe token string for DB storage."""
    token = _fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("ascii")


def decrypt_key(ciphertext: str) -> str:
    """Decrypt a value produced by :func:`encrypt_key`."""
    return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
