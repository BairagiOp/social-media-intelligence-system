"""SMDPIS FastAPI application entrypoint."""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.bootstrap import start_background_bootstrap
from app.config import settings
from app.database import init_db
from app.routers import analysis, dashboard, datasets, evidence, health, ml, network, reports
from app.utils.errors import APIError

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("smdpis")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.ensure_dirs()
    init_db()
    start_background_bootstrap()
    logger.info("SMDPIS backend started (env=%s, version=%s)", settings.env, __version__)
    yield


app = FastAPI(
    title="SMDPIS — Social Media Data Parser & Intelligence System",
    description=(
        "Authorized/public-data social-media intelligence platform. "
        "Works with public datasets, user uploads and synthetic data only."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, duration_ms
    )
    return response


@app.exception_handler(APIError)
async def api_error_handler(request: Request, exc: APIError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    first = errors[0] if errors else {}
    loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    msg = first.get("msg", "Invalid request.")
    return JSONResponse(
        status_code=422,
        content={
            "detail": f"Validation error on {loc}: {msg}" if loc else msg,
            "code": "validation_error",
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An internal server error occurred. Check backend logs for details.",
            "code": "internal_error",
        },
    )


app.include_router(health.router)
app.include_router(datasets.router)
app.include_router(evidence.router)
app.include_router(analysis.router)
app.include_router(network.router)
app.include_router(ml.router)
app.include_router(reports.router)
app.include_router(dashboard.router)


@app.get("/api/meta")
def meta():
    """Static app metadata (tasks, limits) for the frontend."""
    from app.ml.trainer import TASKS
    from app.utils.column_detect import CANONICAL_COLUMNS

    return {
        "name": "SMDPIS",
        "version": __version__,
        "max_upload_mb": settings.max_upload_mb,
        "allowed_extensions": sorted(settings.allowed_extensions),
        "tasks": TASKS,
        "canonical_columns": CANONICAL_COLUMNS,
    }
