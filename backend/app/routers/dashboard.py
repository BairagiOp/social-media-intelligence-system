"""Dashboard summary endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import DashboardSummary
from app.services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary(dataset_id: str | None = Query(None), db: Session = Depends(get_db)):
    return DashboardSummary(**dashboard_service.build_summary(db, dataset_id))
