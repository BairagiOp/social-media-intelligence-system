"""Report endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ReportDetail, ReportListResponse, ReportOut, ReportRequest
from app.services import report_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("", response_model=ReportListResponse)
def list_reports(db: Session = Depends(get_db)):
    items = report_service.list_reports(db)
    return ReportListResponse(
        items=[ReportOut(**r.to_dict()) for r in items], total=len(items)
    )


@router.post("", response_model=ReportDetail, status_code=201)
def create_report(body: ReportRequest, db: Session = Depends(get_db)):
    record = report_service.create_report(db, body.dataset_id, body.title)
    return ReportDetail(
        id=record.id,
        title=record.title,
        dataset_id=record.dataset_id,
        created_at=record.created_at.isoformat() if record.created_at else None,
        content=record.content,
        markdown=record.markdown,
    )


@router.get("/{report_id}", response_model=ReportDetail)
def get_report(report_id: str, db: Session = Depends(get_db)):
    record = report_service.get_report(db, report_id)
    return ReportDetail(
        id=record.id,
        title=record.title,
        dataset_id=record.dataset_id,
        created_at=record.created_at.isoformat() if record.created_at else None,
        content=record.content,
        markdown=record.markdown,
    )
