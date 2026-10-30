"""Pydantic request/response schemas shared across the API."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ErrorBody(BaseModel):
    detail: str
    code: str = "error"


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    database: str
    bootstrap: dict[str, Any] = Field(default_factory=dict)
    models: dict[str, Any] = Field(default_factory=dict)


# --- Datasets ---------------------------------------------------------------

class DatasetSummary(BaseModel):
    id: str
    name: str
    filename: str
    format: str
    records: int
    columns: int
    status: str
    version: int
    parent_id: Optional[str] = None
    evidence_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DatasetDetail(DatasetSummary):
    column_names: list[str] = Field(default_factory=list)
    column_map: dict[str, str] = Field(default_factory=dict)
    profile: Optional[dict[str, Any]] = None
    notes: Optional[str] = None
    has_processed: bool = False


class DatasetListResponse(BaseModel):
    items: list[DatasetSummary]
    total: int


class ProfileResponse(BaseModel):
    dataset_id: str
    profile: dict[str, Any]


class PreprocessOptions(BaseModel):
    deduplicate: bool = True
    drop_missing_text: bool = True
    impute_numeric: bool = True
    lowercase: bool = True
    handle_urls: Literal["placeholder", "strip", "keep"] = "placeholder"
    handle_mentions: Literal["strip", "placeholder", "keep"] = "strip"
    handle_hashtags: Literal["unwrap", "strip", "keep"] = "unwrap"
    handle_emoji: bool = True
    remove_stopwords: bool = False
    lemmatize: bool = False
    feature_engineering: bool = True


class PreprocessRequest(BaseModel):
    options: PreprocessOptions = Field(default_factory=PreprocessOptions)


class PreprocessResponse(BaseModel):
    dataset: DatasetDetail
    report: dict[str, Any]


class ColumnMapRequest(BaseModel):
    mapping: dict[str, str] = Field(default_factory=dict)


class RowsQuery(BaseModel):
    search: Optional[str] = None
    platform: Optional[str] = None
    username: Optional[str] = None
    sentiment: Optional[str] = None
    classification: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    sort_by: Optional[str] = None
    sort_order: Literal["asc", "desc"] = "asc"
    page: int = 1
    page_size: int = 50


class RowsResponse(BaseModel):
    items: list[dict[str, Any]]
    total: int
    total_filtered: int
    page: int
    page_size: int
    pages: int
    columns: list[str]


class DiscoveryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    source: str
    license: str
    dataset_type: str
    records: Optional[str] = None
    required_columns: list[str] = Field(default_factory=list)
    ml_task: str
    link: str
    labels_available: bool = False
    notes: Optional[str] = None
    category: Optional[str] = None
    locally_available: bool = False


class DiscoveryResponse(BaseModel):
    categories: list[dict[str, Any]]
    datasets: list[DiscoveryItem]
    note: str


class SampleLoadResponse(BaseModel):
    dataset: DatasetDetail
    message: str


# --- Web collection ----------------------------------------------------------

class FetchRequest(BaseModel):
    """Download a public dataset file from a URL."""

    url: str = Field(..., max_length=2048, description="http(s) URL of a public dataset file.")
    name: Optional[str] = Field(None, max_length=255)
    license: Optional[str] = Field(None, max_length=200, description="Recorded provenance only.")


class CollectRequest(BaseModel):
    """Pull records from an official public platform API."""

    source: str = Field(..., description="Source id from GET /api/datasets/sources.")
    params: dict[str, Any] = Field(default_factory=dict)
    name: Optional[str] = Field(None, max_length=255)
    license: Optional[str] = Field(None, max_length=200)


class CollectField(BaseModel):
    name: str = Field(..., pattern=r"^[A-Za-z][A-Za-z0-9_]{0,40}$")
    selector: str = Field(..., max_length=300)
    match_all: bool = False
    attribute: Optional[str] = Field(None, max_length=60, description="e.g. href, src, content")


class CrawlRequest(BaseModel):
    """Breadth-first same-site crawl with CSS-selector extraction."""

    url: str = Field(..., max_length=2048)
    name: Optional[str] = Field(None, max_length=255)
    fields: list[CollectField] = Field(..., min_length=1, max_length=20)
    link_selector: str = Field("a[href]", max_length=300)
    max_pages: Optional[int] = Field(None, ge=1, le=200)
    max_depth: Optional[int] = Field(None, ge=0, le=10)
    delay_seconds: Optional[float] = Field(None, ge=0, le=30)
    allow_domains: Optional[list[str]] = Field(None, max_length=20)
    license: Optional[str] = Field(None, max_length=200)


class SourceParam(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    label: str
    required: bool = False
    type: str = "text"
    placeholder: Optional[str] = None
    default: Optional[Any] = None


class SourceSpecOut(BaseModel):
    id: str
    label: str
    description: str
    endpoint: str
    auth_required: bool
    license_note: str
    params: list[dict[str, Any]] = Field(default_factory=list)


class SourcesResponse(BaseModel):
    sources: list[SourceSpecOut]
    policy: dict[str, Any] = Field(default_factory=dict)


class CollectResponse(BaseModel):
    dataset: DatasetDetail
    collection: dict[str, Any] = Field(default_factory=dict)
    message: str


# --- Evidence ---------------------------------------------------------------

class EvidenceOut(BaseModel):
    id: str
    evidence_id: str
    filename: str
    sha256: str
    size_bytes: int
    dataset_id: Optional[str] = None
    status: str
    uploaded_at: Optional[str] = None


class EvidenceListResponse(BaseModel):
    items: list[EvidenceOut]
    total: int


class AuditEventOut(BaseModel):
    id: int
    evidence_id: str
    event: str
    details: dict[str, Any] = Field(default_factory=dict)
    signature: str
    created_at: Optional[str] = None


class AuditLogResponse(BaseModel):
    evidence_id: str
    items: list[AuditEventOut]
    total: int
    integrity: dict[str, Any] = Field(default_factory=dict)


# --- Analysis ---------------------------------------------------------------

class DatasetScopedRequest(BaseModel):
    dataset_id: str


class SentimentResponse(BaseModel):
    dataset_id: str
    disclaimer: str
    total: int
    overall: dict[str, Any]
    timeline: list[dict[str, Any]]
    by_platform: dict[str, Any]
    by_user: dict[str, Any]
    most_positive: list[dict[str, Any]]
    most_negative: list[dict[str, Any]]


class TopicsRequest(BaseModel):
    dataset_id: str
    n_topics: int = Field(6, ge=2, le=20)
    top_terms: int = Field(10, ge=3, le=25)


class TopicsResponse(BaseModel):
    dataset_id: str
    n_topics: int
    topics: list[dict[str, Any]]
    distribution: dict[str, int]
    relations: list[dict[str, Any]]
    quality: dict[str, Any]


class BotResponse(BaseModel):
    dataset_id: str
    disclaimer: str
    model: dict[str, Any]
    accounts: list[dict[str, Any]]
    distribution: dict[str, Any]


class MisinformationRequest(BaseModel):
    dataset_id: str
    limit: int = Field(500, ge=1, le=5000)


class MisinformationResponse(BaseModel):
    dataset_id: str
    disclaimer: str
    model: dict[str, Any]
    summary: dict[str, Any]
    items: list[dict[str, Any]]


# --- Network ----------------------------------------------------------------

class GraphQuery(BaseModel):
    dataset_id: str
    edge_types: list[str] = Field(default_factory=lambda: ["mention", "reply", "share"])
    min_weight: int = Field(1, ge=1)
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    max_nodes: int = Field(300, ge=10, le=1000)


class GraphResponse(BaseModel):
    dataset_id: str
    disclaimer: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    stats: dict[str, Any]
    communities: dict[str, Any]
    centrality: dict[str, Any]


# --- ML ---------------------------------------------------------------------

class TrainRequest(BaseModel):
    dataset_id: str
    task: Literal["sentiment", "bot_detection", "misinformation", "topic_model"]
    target: Optional[str] = None
    features: Optional[list[str]] = None
    model_type: Optional[str] = None
    test_size: float = Field(0.2, gt=0.05, lt=0.9)
    n_topics: int = Field(6, ge=2, le=20)
    max_features: int = Field(5000, ge=500, le=50000)
    name: Optional[str] = None


class JobOut(BaseModel):
    job_id: str
    task: Optional[str] = None
    dataset_id: Optional[str] = None
    status: str
    progress: int
    step: str
    detail: str
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    created_at: Optional[str] = None


class ModelOut(BaseModel):
    id: str
    model_id: str
    name: str
    task: str
    dataset_id: Optional[str] = None
    version: int
    metrics: dict[str, Any] = Field(default_factory=dict)
    features: list[Any] = Field(default_factory=list)
    artifact_path: str
    status: str
    created_at: Optional[str] = None


class ModelListResponse(BaseModel):
    items: list[ModelOut]
    total: int


class TaskCatalogResponse(BaseModel):
    tasks: dict[str, Any]


class InferRequest(BaseModel):
    dataset_id: Optional[str] = None
    task: Literal["sentiment", "bot_detection", "misinformation"]
    texts: Optional[list[str]] = None
    limit: int = Field(500, ge=1, le=5000)


# --- Dashboard --------------------------------------------------------------

class DashboardSummary(BaseModel):
    dataset_id: Optional[str] = None
    total_records: int = 0
    active_datasets: int = 0
    accounts_analyzed: int = 0
    automated_likelihood: Optional[dict[str, Any]] = None
    flagged_content: Optional[dict[str, Any]] = None
    topic_count: int = 0
    evidence_items: int = 0
    model_accuracy: Optional[dict[str, Any]] = None
    activity_timeline: list[dict[str, Any]] = Field(default_factory=list)
    sentiment_timeline: list[dict[str, Any]] = Field(default_factory=list)
    platform_distribution: dict[str, int] = Field(default_factory=dict)
    bot_distribution: Optional[dict[str, Any]] = None
    topic_distribution: dict[str, int] = Field(default_factory=dict)
    engagement_trend: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# --- Reports ----------------------------------------------------------------

class ReportRequest(BaseModel):
    dataset_id: Optional[str] = None
    title: Optional[str] = None


class ReportOut(BaseModel):
    id: str
    title: str
    dataset_id: Optional[str] = None
    created_at: Optional[str] = None
    sections: list[str] = Field(default_factory=list)


class ReportListResponse(BaseModel):
    items: list[ReportOut]
    total: int


class ReportDetail(BaseModel):
    id: str
    title: str
    dataset_id: Optional[str] = None
    created_at: Optional[str] = None
    content: dict[str, Any] = Field(default_factory=dict)
    markdown: str = ""
