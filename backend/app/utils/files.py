"""Reusable file utilities: validation, safe storage, hashing helpers."""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from pathlib import Path

from app.config import settings


class FileValidationError(ValueError):
    """Raised when an uploaded file fails validation."""


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str, salt: str = "") -> str:
    return hashlib.sha256((salt + text).encode("utf-8", errors="replace")).hexdigest()


def validate_extension(filename: str) -> str:
    ext = Path(filename or "").suffix.lower().lstrip(".")
    if not ext:
        raise FileValidationError("File has no extension.")
    if ext not in settings.allowed_extensions:
        raise FileValidationError(
            f"Unsupported file type '.{ext}'. Allowed: "
            f"{', '.join(sorted(settings.allowed_extensions))}."
        )
    return ext


def validate_size(size_bytes: int) -> None:
    limit = settings.max_upload_mb * 1024 * 1024
    if size_bytes > limit:
        raise FileValidationError(
            f"File exceeds the {settings.max_upload_mb} MB upload limit."
        )
    if size_bytes == 0:
        raise FileValidationError("Uploaded file is empty.")


def safe_stem(filename: str) -> str:
    stem = Path(filename).stem
    stem = re.sub(r"[^A-Za-z0-9._-]", "_", stem)[:80] or "dataset"
    return stem


def store_upload(content: bytes, filename: str) -> tuple[str, str]:
    """Persist raw upload bytes (immutable evidence copy). Returns (path, extension)."""
    ext = validate_extension(filename)
    validate_size(len(content))
    settings.ensure_dirs()
    stored_name = f"{uuid.uuid4().hex}_{safe_stem(filename)}.{ext}"
    dest = settings.raw_dir / stored_name
    dest.write_bytes(content)
    return str(dest), ext


def read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
