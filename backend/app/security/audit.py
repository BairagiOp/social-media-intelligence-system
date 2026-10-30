"""Append-only, HMAC-signed audit trail for chain of custody."""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.evidence import AuditEvent
from app.security.hashing import sign_payload

logger = logging.getLogger(__name__)

VALID_EVENTS = {
    "UPLOAD",
    "FETCH",
    "HASH",
    "VALIDATE",
    "PREPROCESS",
    "ANALYZE",
    "MODEL",
    "EXPORT",
    "DELETE",
    "MAP_COLUMNS",
    "REPORT",
}


def record_event(db: Session, evidence_id: str, event: str, details: dict | None = None) -> AuditEvent:
    details = details or {}
    payload = {"evidence_id": evidence_id, "event": event, "details": details}
    entry = AuditEvent(
        evidence_id=evidence_id,
        event=event,
        details=details,
        signature=sign_payload(payload),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    logger.info("Audit event %s recorded for evidence %s", event, evidence_id)
    return entry
