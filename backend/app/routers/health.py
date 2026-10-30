"""Health & readiness endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.app_state import bootstrap_state
from app.config import settings
from app.database import get_db
from app.ml import registry
from app.ml.trainer import TASKS
from app.schemas import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"

    active = {}
    try:
        for task in TASKS:
            record = registry.get_active(db, task)
            active[task] = record.model_id if record else None
    except Exception:
        active = {}

    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        version=settings.app_version,
        environment=settings.env,
        database=db_status,
        bootstrap=bootstrap_state.to_dict(),
        models=active,
    )
