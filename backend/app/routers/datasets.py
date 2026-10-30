"""Dataset endpoints: upload, discovery, web collection, profile, preprocessing, explorer."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.schemas import (
    CollectRequest,
    CollectResponse,
    ColumnMapRequest,
    CrawlRequest,
    DatasetDetail,
    DatasetListResponse,
    DatasetSummary,
    DiscoveryResponse,
    FetchRequest,
    PreprocessRequest,
    PreprocessResponse,
    ProfileResponse,
    RowsResponse,
    SampleLoadResponse,
    SourcesResponse,
)
from app.security.audit import record_event
from app.services import crawl_service, dataset_service, fetch_service, web_sources
from app.services.crawl_service import FieldSpec
from app.utils.errors import NotFoundError, ValidationFailed

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("", response_model=DatasetListResponse)
def list_datasets(db: Session = Depends(get_db)):
    items = dataset_service.list_datasets(db)
    return DatasetListResponse(
        items=[DatasetSummary(**d.to_summary()) for d in items], total=len(items)
    )


@router.post("/upload", response_model=DatasetDetail, status_code=201)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(None),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise ValidationFailed("No file was provided.")
    content = await file.read()
    dataset = dataset_service.ingest_bytes(
        db, content, file.filename, name=name or file.filename, source="upload"
    )
    return DatasetDetail(**dataset.to_detail())


@router.post("/sample", response_model=SampleLoadResponse, status_code=201)
def load_sample_dataset(db: Session = Depends(get_db)):
    """Load the bundled synthetic sample dataset (generated on demand)."""
    from app.bootstrap import ensure_sample_dataset

    dataset = ensure_sample_dataset(db)
    return SampleLoadResponse(
        dataset=DatasetDetail(**dataset.to_detail()),
        message="Sample dataset loaded.",
    )


@router.get("/discovery", response_model=DiscoveryResponse)
def dataset_discovery():
    catalog_path: Path = settings.catalog_path
    if not catalog_path.exists():
        raise NotFoundError("Dataset catalog not available.")
    with open(catalog_path, "r", encoding="utf-8") as fh:
        catalog = json.load(fh)
    return DiscoveryResponse(
        categories=catalog.get("categories", []),
        datasets=catalog.get("datasets", []),
        note=catalog.get(
            "note",
            "Datasets are recommendations only — download manually from the "
            "linked sources and upload them here.",
        ),
    )


# ---------------------------------------------------------------------------
# Web collection (public sources only)
# ---------------------------------------------------------------------------

def _describe(method: str, provenance: dict) -> str:
    if method == "fetch":
        return (
            f"Fetched {provenance.get('final_url')} at {provenance.get('fetched_at')} "
            f"(HTTP {provenance.get('http_status')}, {provenance.get('size_bytes')} bytes, "
            f"robots allowed: {provenance.get('robots_allowed')})."
        )
    if method == "collect":
        return (
            f"Collected {provenance.get('records')} records from "
            f"{provenance.get('source')} via its public API at {provenance.get('fetched_at')}."
        )
    return (
        f"Crawled {provenance.get('pages_crawled')} page(s) from "
        f"{provenance.get('start_url')} producing {provenance.get('records')} record(s)."
    )


def _finish(
    db: Session,
    *,
    content: bytes,
    filename: str,
    name: str | None,
    method: str,
    provenance: dict,
    message: str,
) -> CollectResponse:
    """Run collected bytes through the standard immutable ingest, then custody-log provenance."""
    dataset = dataset_service.ingest_bytes(db, content, filename, name=name, source=method)

    summary = _describe(method, provenance)
    dataset.notes = f"{dataset.notes}\n{summary}".strip() if dataset.notes else summary
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    if dataset.evidence_id:
        record_event(
            db,
            dataset.evidence_id,
            "FETCH",
            {"dataset_id": dataset.id, "method": method, **provenance},
        )
    logger.info("Collected dataset %s via %s (%s records)", dataset.id, method, dataset.records)

    return CollectResponse(
        dataset=DatasetDetail(**dataset.to_detail()),
        collection={**provenance, "dataset_id": dataset.id},
        message=message,
    )


@router.get("/sources", response_model=SourcesResponse)
def list_sources():
    """Catalog of official public API connectors plus the outbound fetch policy."""
    from app.services.web_sources import list_sources as _registry

    return SourcesResponse(
        sources=_registry(),
        policy={
            "enabled": settings.fetch_enabled,
            "schemes": ["http", "https"],
            "robots_obeyed": settings.fetch_robots_obey,
            "private_targets_blocked": not settings.fetch_allow_private,
            "max_mb": settings.fetch_max_mb,
            "timeout_seconds": settings.fetch_timeout,
            "max_redirects": settings.fetch_max_redirects,
            "min_interval_seconds": settings.fetch_min_interval,
            "crawl_max_pages": settings.crawl_max_pages,
            "crawl_max_depth": settings.crawl_max_depth,
            "max_items": settings.collect_max_items,
            "host_allowlist": sorted(settings.fetch_host_allowlist),
            "blocked_domains": sorted(fetch_service.BLOCKED_DOMAINS),
            "statement": (
                "SMDPIS contacts only public sources that publish automated-read "
                "endpoints or permit access in robots.txt. It never authenticates, "
                "never bypasses access controls and never stores credentials."
            ),
        },
    )


@router.post("/fetch", response_model=CollectResponse, status_code=201)
def fetch_remote_dataset(body: FetchRequest, db: Session = Depends(get_db)):
    """Download a public dataset file (CSV/JSON/JSONL/Parquet) from a URL."""
    resource = fetch_service.fetch_url(body.url)

    name = body.name or Path(resource.filename).stem
    provenance = resource.provenance()
    if body.license:
        provenance["license"] = body.license

    return _finish(
        db,
        content=resource.content,
        filename=resource.filename,
        name=name,
        method="fetch",
        provenance=provenance,
        message=f"Fetched {resource.size_bytes:,} bytes from {resource.url}.",
    )


@router.post("/collect", response_model=CollectResponse, status_code=201)
def collect_from_source(body: CollectRequest, db: Session = Depends(get_db)):
    """Pull records from an official, unauthenticated public platform API."""
    records = web_sources.collect(body.source, body.params)
    if len(records) > settings.collect_max_items:
        records = records[: settings.collect_max_items]

    filename = f"{body.source}_collection.csv"
    content = fetch_service.records_to_csv(records, filename)

    provenance = {
        "method": "collect",
        "source": body.source,
        "records": len(records),
        "params": {k: v for k, v in (body.params or {}).items() if v not in (None, "")},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "auth_used": False,
    }
    if body.license:
        provenance["license"] = body.license

    return _finish(
        db,
        content=content,
        filename=filename,
        name=body.name or f"{body.source} collection",
        method="collect",
        provenance=provenance,
        message=f"Collected {len(records)} records from {body.source}.",
    )


@router.post("/crawl", response_model=CollectResponse, status_code=201)
def crawl_page(body: CrawlRequest, db: Session = Depends(get_db)):
    """Breadth-first same-site crawl with CSS-selector extraction."""
    field_specs = [
        FieldSpec(
            name=f.name,
            selector=f.selector,
            match_all=f.match_all,
            attribute=f.attribute,
        )
        for f in body.fields
    ]
    records, stats = crawl_service.crawl(
        body.url,
        fields=field_specs,
        link_selector=body.link_selector,
        max_pages=body.max_pages,
        max_depth=body.max_depth,
        delay=body.delay_seconds,
        allow_domains=body.allow_domains,
    )

    filename = "crawl_collection.csv"
    content = fetch_service.records_to_csv(records, filename)

    provenance = {"method": "crawl", **stats}
    if body.license:
        provenance["license"] = body.license

    return _finish(
        db,
        content=content,
        filename=filename,
        name=body.name or f"Crawl of {stats['allowed_domains'][0]}",
        method="crawl",
        provenance=provenance,
        message=(
            f"Crawled {stats['pages_crawled']} page(s), "
            f"extracted {len(records)} record(s)."
        ),
    )


@router.get("/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: str, db: Session = Depends(get_db)):
    dataset = dataset_service.get_dataset(db, dataset_id)
    return DatasetDetail(**dataset.to_detail())


@router.get("/{dataset_id}/profile", response_model=ProfileResponse)
def get_profile(
    dataset_id: str,
    refresh: bool = Query(False),
    db: Session = Depends(get_db),
):
    profile = dataset_service.get_profile(db, dataset_id, refresh=refresh)
    return ProfileResponse(dataset_id=dataset_id, profile=profile)


@router.post("/{dataset_id}/column-map", response_model=DatasetDetail)
def set_column_map(dataset_id: str, body: ColumnMapRequest, db: Session = Depends(get_db)):
    dataset = dataset_service.update_column_map(db, dataset_id, body.mapping)
    return DatasetDetail(**dataset.to_detail())


@router.post("/{dataset_id}/preprocess", response_model=PreprocessResponse)
def preprocess(dataset_id: str, body: PreprocessRequest, db: Session = Depends(get_db)):
    child, report = dataset_service.preprocess_dataset(
        db, dataset_id, body.options.model_dump()
    )
    return PreprocessResponse(
        dataset=DatasetDetail(**child.to_detail()), report=report
    )


@router.get("/{dataset_id}/rows", response_model=RowsResponse)
def query_rows(
    dataset_id: str,
    search: str | None = None,
    platform: str | None = None,
    username: str | None = None,
    sentiment: str | None = None,
    classification: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    dataset = dataset_service.get_dataset(db, dataset_id)
    df = dataset_service.dataset_frame(dataset)
    result = dataset_service.query_rows(
        df,
        dataset.column_map or {},
        search=search,
        platform=platform,
        username=username,
        sentiment=sentiment,
        classification=classification,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    return RowsResponse(**result)


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, db: Session = Depends(get_db)):
    dataset = dataset_service.delete_dataset(db, dataset_id)
    return {
        "deleted": True,
        "id": dataset.id,
        "message": "Dataset marked deleted. Evidence files and audit history preserved.",
    }
