"""Hashing and integrity helpers.

Hash values are the forensic anchor of the whole application: originals are
hashed at ingestion, re-verified on demand, and every derived record can be
traced back to an evidence source hash.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

CHUNK = 1024 * 1024


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def message_fingerprint(*parts: str) -> str:
    """Deterministic message identity used for duplicate detection.

    Deliberately independent of case id so that the same record imported twice
    (or present in two snapshots of one conversation) collides.
    """
    joined = "\x1f".join(p or "" for p in parts)
    return sha256_text(joined)


def verify_file(path: Path | str, expected: str) -> bool:
    p = Path(path)
    if not p.is_file():
        return False
    return sha256_file(p) == expected
