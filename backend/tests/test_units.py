"""Unit tests: text preprocessing, column detection, SHA-256 helpers."""
from __future__ import annotations

import hashlib

from app.security.hashing import sha256_bytes, sign_payload, verify_signature
from app.utils.column_detect import detect_columns
from app.utils.files import FileValidationError, validate_extension, validate_size
from app.utils.text_cleaning import clean_text, redact_ips


def test_clean_text_lowercases_and_strips_urls():
    out = clean_text("Check HTTPS://Example.com/a Now", handle_urls="strip")
    assert "http" not in out.lower()
    assert out == out.lower()


def test_clean_text_handles_mentions_hashtags_emoji():
    out = clean_text("Hey @alice check #Python 🎉 great!")
    assert "@alice" not in out
    assert "python" in out.lower()
    assert "🎉" not in out


def test_clean_text_placeholder_options():
    assert "url" in clean_text("see https://x.example/path", handle_urls="placeholder")
    assert "userhandle" in clean_text("hi @bob", handle_mentions="placeholder")


def test_raw_text_not_mutated_input():
    original = "Hello @World #Tag 😀"
    clean_text(original)
    assert original == "Hello @World #Tag 😀"


def test_redact_ips():
    out = redact_ips("connect from 192.168.10.42 and 10.0.0.1 now")
    assert "192.168.10.42" not in out
    assert "10.0.0.1" not in out
    assert "[redacted-ip]" in out


def test_detect_columns():
    mapping = detect_columns(
        ["Tweet", "screen_name", "created_at", "favorite_count", "sentiment", "irrelevant"]
    )
    assert mapping["text"] == "Tweet"
    assert mapping["username"] == "screen_name"
    assert mapping["timestamp"] == "created_at"
    assert mapping["likes"] == "favorite_count"
    assert mapping["label"] == "sentiment"
    assert "irrelevant" not in mapping.values()


def test_file_validation():
    assert validate_extension("posts.CSV") == "csv"
    try:
        validate_extension("posts.exe")
        assert False, "should raise"
    except FileValidationError:
        pass
    try:
        validate_size(0)
        assert False, "should raise"
    except FileValidationError:
        pass


def test_sha256_and_hmac():
    data = b"smdpis evidence"
    assert sha256_bytes(data) == hashlib.sha256(data).hexdigest()
    payload = {"event": "HASH", "value": "abc"}
    sig = sign_payload(payload)
    assert len(sig) == 64
    assert verify_signature(payload, sig)
    assert not verify_signature(payload, "0" * 64)
