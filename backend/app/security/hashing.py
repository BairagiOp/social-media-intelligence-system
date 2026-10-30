"""Security helpers: hashing and HMAC audit signatures."""
from __future__ import annotations

import hashlib
import hmac
import json

from app.config import settings


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_sha256(path: str, expected: str) -> bool:
    return hmac.compare_digest(sha256_file(path), expected.lower())


def sign_payload(payload: dict) -> str:
    """HMAC-SHA256 signature of a canonical JSON payload using the server secret."""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hmac.new(
        settings.secret_key.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_signature(payload: dict, signature: str) -> bool:
    return hmac.compare_digest(sign_payload(payload), signature or "")


def fingerprint(text: str) -> str:
    """Salted one-way fingerprint (used to redact sensitive values like IPs)."""
    salted = f"{settings.secret_key}:{text}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()[:16]
