"""Evidence management: SHA-256 chain of custody for ingested files."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.evidence import AuditEvent, Evidence
from app.security.audit import record_event
from app.security.hashing import sha256_file, verify_sha256, verify_signature
from app.utils.errors import NotFoundError

logger = logging.getLogger(__name__)


def _new_evidence_id(db: Session) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    for _ in range(20):
        candidate = f"EV-{stamp}-{uuid.uuid4().hex[:6].upper()}"
        exists = db.scalar(select(Evidence).where(Evidence.evidence_id == candidate))
        if not exists:
            return candidate
    raise RuntimeError("Could not allocate a unique evidence ID.")


def register_evidence(
    db: Session,
    *,
    file_path: str | Path,
    filename: str,
    dataset_id: str | None = None,
    status: str = "HASHED",
    source: str = "upload",
) -> Evidence:
    """Hash an immutable source file and create its custody record."""
    path = Path(file_path)
    digest = sha256_file(path)
    size = path.stat().st_size
    evidence = Evidence(
        evidence_id=_new_evidence_id(db),
        filename=filename,
        sha256=digest,
        size_bytes=size,
        file_path=str(path),
        dataset_id=dataset_id,
        status=status,
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    record_event(
        db,
        evidence.evidence_id,
        "UPLOAD",
        {"filename": filename, "size_bytes": size, "source": source},
    )
    record_event(
        db,
        evidence.evidence_id,
        "HASH",
        {"algorithm": "SHA-256", "value": digest},
    )
    logger.info("Evidence %s registered for %s", evidence.evidence_id, filename)
    return evidence


def attach_dataset(db: Session, evidence: Evidence, dataset_id: str) -> None:
    evidence.dataset_id = dataset_id
    db.add(evidence)
    db.commit()
    db.refresh(evidence)


def list_evidence(db: Session, limit: int = 200) -> list[Evidence]:
    return list(
        db.scalars(
            select(Evidence).order_by(Evidence.uploaded_at.desc()).limit(limit)
        ).all()
    )


def get_evidence(db: Session, evidence_pk: str) -> Evidence:
    evidence = db.get(Evidence, evidence_pk) or db.scalar(
        select(Evidence).where(Evidence.evidence_id == evidence_pk)
    )
    if not evidence:
        raise NotFoundError("Evidence item not found.")
    return evidence


def audit_log(db: Session, evidence: Evidence) -> list[AuditEvent]:
    return list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.evidence_id == evidence.evidence_id)
            .order_by(AuditEvent.id.asc())
        ).all()
    )


def verify_integrity(evidence: Evidence) -> dict:
    """Recompute the file hash and compare with the recorded value."""
    path = Path(evidence.file_path)
    if not path.exists():
        return {
            "verified": False,
            "reason": "Source file is no longer present on this server.",
        }
    matches = verify_sha256(str(path), evidence.sha256)
    return {
        "verified": matches,
        "algorithm": "SHA-256",
        "recorded_sha256": evidence.sha256,
        "current_sha256": sha256_file(str(path)),
        "reason": "Hash match — evidence unchanged." if matches else "Hash mismatch!",
    }


def verify_chain(events: list[AuditEvent]) -> dict:
    """Re-validate the HMAC-SHA256 signature of every audit event for an evidence item."""
    invalid: list[dict] = []
    for index, entry in enumerate(events):
        payload = {
            "evidence_id": entry.evidence_id,
            "event": entry.event,
            "details": entry.details or {},
        }
        if not verify_signature(payload, entry.signature):
            invalid.append({"index": index, "event": entry.event})
    return {
        "valid": not invalid,
        "events_checked": len(events),
        "tampered": invalid,
        "reason": (
            "All audit signatures valid — chain intact."
            if not invalid
            else f"{len(invalid)} audit event(s) failed signature verification."
        ),
    }
