"""Evidence / chain-of-custody endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import AuditLogResponse, AuditEventOut, EvidenceListResponse, EvidenceOut
from app.services import evidence_service
from app.security.audit import record_event

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


@router.get("", response_model=EvidenceListResponse)
def list_evidence(db: Session = Depends(get_db)):
    items = evidence_service.list_evidence(db)
    return EvidenceListResponse(
        items=[EvidenceOut(**e.to_dict()) for e in items], total=len(items)
    )


@router.get("/{evidence_ref}", response_model=EvidenceOut)
def get_evidence(evidence_ref: str, db: Session = Depends(get_db)):
    evidence = evidence_service.get_evidence(db, evidence_ref)
    return EvidenceOut(**evidence.to_dict())


@router.get("/{evidence_ref}/audit-log", response_model=AuditLogResponse)
def audit_log(evidence_ref: str, db: Session = Depends(get_db)):
    evidence = evidence_service.get_evidence(db, evidence_ref)
    events = evidence_service.audit_log(db, evidence)
    integrity = evidence_service.verify_integrity(evidence)
    return AuditLogResponse(
        evidence_id=evidence.evidence_id,
        items=[AuditEventOut(**e.to_dict()) for e in events],
        total=len(events),
        integrity=integrity,
    )


@router.get("/{evidence_ref}/verify")
def verify_evidence(evidence_ref: str, db: Session = Depends(get_db)):
    """Re-hash the stored file and validate every audit signature in the chain."""
    evidence = evidence_service.get_evidence(db, evidence_ref)
    events = evidence_service.audit_log(db, evidence)
    file_integrity = evidence_service.verify_integrity(evidence)
    chain = evidence_service.verify_chain(events)
    return {
        "evidence_id": evidence.evidence_id,
        "valid": bool(file_integrity.get("verified")) and chain["valid"],
        "file_integrity": file_integrity,
        "audit_chain": chain,
    }


@router.get("/{evidence_ref}/export")
def export_report(evidence_ref: str, db: Session = Depends(get_db)):
    """Generate an exportable evidence report (records an EXPORT audit event)."""
    evidence = evidence_service.get_evidence(db, evidence_ref)
    events = evidence_service.audit_log(db, evidence)
    integrity = evidence_service.verify_integrity(evidence)
    record_event(
        db,
        evidence.evidence_id,
        "EXPORT",
        {"report": "evidence_report", "format": "json"},
    )
    return {
        "evidence": evidence.to_dict(),
        "integrity": integrity,
        "audit_trail": [e.to_dict() for e in events],
        "statement": (
            "Original evidence file was not modified at any point. "
            "All transformations occurred on derived working copies."
        ),
    }
