"""Dataset ingestion, profiling, preprocessing, versioning and querying."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.loader import load_dataframe
from app.config import settings
from app.models.dataset import Dataset
from app.security.audit import record_event
from app.services import evidence_service
from app.utils.column_detect import apply_mapping, detect_columns
from app.utils.errors import NotFoundError, ValidationFailed
from app.utils.files import safe_stem, store_upload
from app.utils.profiling import build_profile
from app.utils.text_cleaning import clean_text, redact_ips

logger = logging.getLogger(__name__)

IP_LIKE_COLUMNS = {"ip", "ip_address", "source_ip", "client_ip", "ip_addr", "remote_ip"}


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def ingest_bytes(
    db: Session,
    content: bytes,
    filename: str,
    name: str | None = None,
    source: str = "upload",
) -> Dataset:
    try:
        file_path, ext = store_upload(content, filename)
    except ValueError as exc:
        raise ValidationFailed(str(exc)) from exc
    return _ingest_file(db, Path(file_path), filename, ext, name, source)


def ingest_existing_file(
    db: Session, file_path: str | Path, name: str | None = None, source: str = "sample"
) -> Dataset:
    file_path = Path(file_path)
    if not file_path.exists():
        raise ValidationFailed(f"Sample file not found: {file_path.name}")
    ext = file_path.suffix.lstrip(".").lower()
    if ext not in settings.allowed_extensions:
        raise ValidationFailed(f"Unsupported sample file type '.{ext}'.")
    return _ingest_file(db, file_path, file_path.name, ext, name or file_path.stem, source)


def _ingest_file(
    db: Session,
    file_path: Path,
    filename: str,
    ext: str,
    name: str | None,
    source: str,
) -> Dataset:
    evidence = evidence_service.register_evidence(
        db, file_path=file_path, filename=filename, source=source
    )
    try:
        df = load_dataframe(file_path, ext)
    except ValidationFailed:
        evidence.status = "REJECTED"
        db.add(evidence)
        db.commit()
        record_event(db, evidence.evidence_id, "VALIDATE", {"result": "FAILED"})
        raise

    record_event(
        db,
        evidence.evidence_id,
        "VALIDATE",
        {"result": "PASSED", "records": int(len(df)), "columns": int(df.shape[1])},
    )

    columns = [str(c) for c in df.columns]
    mapping = detect_columns(columns)

    # Redact sensitive columns (e.g. IP addresses) in the working copy only;
    # the original evidence file is never modified.
    df = _redact_dataframe(df)

    working_path = settings.processed_dir / f"raw_{uuid_hex()}.parquet"
    _save_frame(df, working_path)

    dataset = Dataset(
        name=name or Path(filename).stem,
        filename=filename,
        format=ext,
        file_path=str(file_path),
        processed_path=str(working_path),
        records=int(len(df)),
        columns=columns,
        column_map=mapping,
        status="VALIDATED",
        evidence_id=evidence.evidence_id,
    )
    dataset.profile = build_profile(df, mapping)
    db.add(dataset)
    db.commit()
    db.refresh(dataset)

    evidence_service.attach_dataset(db, evidence, dataset.id)
    record_event(
        db,
        evidence.evidence_id,
        "VALIDATE",
        {"result": "PROFILED", "dataset_id": dataset.id},
    )
    logger.info("Ingested dataset %s (%s records)", dataset.id, dataset.records)
    return dataset


def uuid_hex() -> str:
    import uuid

    return uuid.uuid4().hex[:16]


def _save_frame(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path, index=False)
    except Exception:
        # Parquet writer unavailable → CSV fallback (still lossless enough for analysis).
        path = path.with_suffix(".csv")
        df.to_csv(path, index=False)


def _redact_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in list(df.columns):
        if str(col).strip().lower() in IP_LIKE_COLUMNS:
            from app.security.hashing import fingerprint

            df[col] = df[col].apply(
                lambda v: f"ip:{fingerprint(str(v))}" if pd.notna(v) else v
            )
    # Redact IPv4 addresses embedded in free text.
    from app.utils.pandas_compat import is_text_series

    for col in df.columns:
        if is_text_series(df[col]):
            sample = df[col].dropna().head(50)
            if any(isinstance(v, str) for v in sample):
                df[col] = df[col].apply(
                    lambda v: redact_ips(v) if isinstance(v, str) else v
                )
    return df


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def list_datasets(db: Session, include_deleted: bool = False) -> list[Dataset]:
    stmt = select(Dataset).order_by(Dataset.created_at.desc())
    items = list(db.scalars(stmt).all())
    if not include_deleted:
        items = [d for d in items if d.status != "DELETED"]
    return items


def get_dataset(db: Session, dataset_id: str) -> Dataset:
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise NotFoundError("Dataset not found.")
    return dataset


def dataset_frame(dataset: Dataset) -> pd.DataFrame:
    """Load the current working frame for a dataset (processed copy preferred)."""
    if dataset.processed_path and Path(dataset.processed_path).exists():
        return load_dataframe(dataset.processed_path)
    return load_dataframe(dataset.file_path, dataset.format)


def get_profile(db: Session, dataset_id: str, refresh: bool = False) -> dict:
    dataset = get_dataset(db, dataset_id)
    if refresh or not dataset.profile:
        df = dataset_frame(dataset)
        dataset.profile = build_profile(df, dataset.column_map or {})
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
    return dataset.profile


def update_column_map(db: Session, dataset_id: str, mapping: dict) -> Dataset:
    dataset = get_dataset(db, dataset_id)
    merged = apply_mapping(list(dataset.columns or []), mapping)
    dataset.column_map = merged
    df = dataset_frame(dataset)
    dataset.profile = build_profile(df, merged)
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    if dataset.evidence_id:
        record_event(
            db,
            dataset.evidence_id,
            "MAP_COLUMNS",
            {"dataset_id": dataset.id, "mapping": merged},
        )
    return dataset


def delete_dataset(db: Session, dataset_id: str) -> Dataset:
    """Soft-delete: evidence files and audit history are always preserved."""
    dataset = get_dataset(db, dataset_id)
    dataset.status = "DELETED"
    dataset.notes = (dataset.notes or "") + "\nDeleted by user."
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    if dataset.evidence_id:
        record_event(
            db, dataset.evidence_id, "DELETE", {"dataset_id": dataset.id}
        )
    return dataset


# ---------------------------------------------------------------------------
# Preprocessing pipeline
# ---------------------------------------------------------------------------

DEFAULT_PREPROCESS_OPTIONS = {
    "deduplicate": True,
    "drop_missing_text": True,
    "impute_numeric": True,
    "lowercase": True,
    "handle_urls": "placeholder",
    "handle_mentions": "strip",
    "handle_hashtags": "unwrap",
    "handle_emoji": True,
    "remove_stopwords": False,
    "lemmatize": False,
    "feature_engineering": True,
}


def preprocess_dataset(
    db: Session, dataset_id: str, options: dict | None = None
) -> tuple[Dataset, dict]:
    opts = {**DEFAULT_PREPROCESS_OPTIONS, **(options or {})}
    parent = get_dataset(db, dataset_id)
    if parent.status == "DELETED":
        raise ValidationFailed("Cannot preprocess a deleted dataset.")

    df = dataset_frame(parent)
    report: dict = {
        "input_records": int(len(df)),
        "steps": [],
        "options": opts,
    }
    mapping = dict(parent.column_map or detect_columns([str(c) for c in df.columns]))

    # 1. Redaction of sensitive fields (always on).
    before_cols = set(df.columns)
    df = _redact_dataframe(df)
    new_cols = set(df.columns) - before_cols
    report["steps"].append({"step": "redaction", "detail": "Sensitive values hashed / IPs redacted"})

    # 2. Duplicate removal
    if opts["deduplicate"]:
        n0 = len(df)
        df = df.drop_duplicates().reset_index(drop=True)
        report["steps"].append(
            {"step": "deduplication", "removed": int(n0 - len(df))}
        )

    # 3. Missing value handling
    text_col = mapping.get("text")
    dropped_missing = 0
    if opts["drop_missing_text"] and text_col and text_col in df.columns:
        n0 = len(df)
        df = df[df[text_col].notna()].reset_index(drop=True)
        dropped_missing = int(n0 - len(df))
    imputed = []
    if opts["impute_numeric"]:
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                median = df[col].median()
                if pd.notna(median) and df[col].isna().any():
                    df[col] = df[col].fillna(median)
                    imputed.append(col)
    from app.utils.pandas_compat import is_text_series

    for col in df.columns:
        if is_text_series(df[col]):
            df[col] = df[col].fillna("")
    report["steps"].append(
        {
            "step": "missing_values",
            "dropped_rows_missing_text": dropped_missing,
            "imputed_numeric_columns": imputed,
        }
    )

    # 4. Text cleaning (original text preserved)
    if text_col and text_col in df.columns:
        clean_kwargs = {
            "lowercase": opts["lowercase"],
            "handle_urls": opts["handle_urls"],
            "handle_mentions": opts["handle_mentions"],
            "handle_hashtags": opts["handle_hashtags"],
            "handle_emoji": opts["handle_emoji"],
            "remove_stopwords": opts["remove_stopwords"],
            "lemmatize": opts["lemmatize"],
        }
        df["text_clean"] = [clean_text(t, **clean_kwargs) for t in df[text_col]]
        mapping["text_clean"] = "text_clean"
        report["steps"].append({"step": "text_cleaning", "column": "text_clean"})

    # 5. Feature engineering
    if opts["feature_engineering"]:
        engineered = _engineer_features(df, mapping)
        report["steps"].append(
            {"step": "feature_engineering", "columns": engineered}
        )

    # Persist as a new dataset version
    version = int(parent.version) + 1
    out_path = settings.processed_dir / f"{parent.id}_v{version}_{uuid_hex()}.parquet"
    _save_frame(df, out_path)

    child = Dataset(
        name=f"{parent.name} (v{version})",
        filename=parent.filename,
        format=parent.format,
        file_path=parent.file_path,          # points at immutable evidence file
        processed_path=str(out_path),
        records=int(len(df)),
        columns=[str(c) for c in df.columns],
        column_map=mapping,
        status="PREPROCESSED",
        version=version,
        parent_id=parent.id,
        evidence_id=parent.evidence_id,
        notes=f"Preprocessed from dataset {parent.id} v{parent.version}",
    )
    child.profile = build_profile(df, mapping)
    db.add(child)
    db.commit()
    db.refresh(child)

    report["output_records"] = int(len(df))
    report["dataset_id"] = child.id
    report["version"] = version

    if child.evidence_id:
        record_event(
            db,
            child.evidence_id,
            "PREPROCESS",
            {
                "from_dataset": parent.id,
                "to_dataset": child.id,
                "input_records": report["input_records"],
                "output_records": report["output_records"],
                "steps": [s["step"] for s in report["steps"]],
            },
        )
    return child, report


def _engineer_features(df: pd.DataFrame, mapping: dict) -> list[str]:
    created: list[str] = []

    def _num(col: str) -> pd.Series | None:
        src = mapping.get(col)
        if src and src in df.columns:
            return pd.to_numeric(df[src], errors="coerce")
        return None

    likes, comments, shares = _num("likes"), _num("comments"), _num("shares")
    followers = _num("followers")
    if likes is not None or comments is not None or shares is not None:
        engagement = (
            (likes if likes is not None else 0)
            + 2 * (comments if comments is not None else 0)
            + 3 * (shares if shares is not None else 0)
        )
        df["engagement_score"] = engagement
        created.append("engagement_score")
        if followers is not None:
            df["engagement_ratio"] = (
                engagement / followers.replace(0, pd.NA)
            ).astype(float).fillna(0.0)
            created.append("engagement_ratio")

    following = _num("following")
    if followers is not None and following is not None:
        df["follower_following_ratio"] = (
            followers / following.replace(0, pd.NA)
        ).astype(float).fillna(0.0)
        created.append("follower_following_ratio")

    text_col = mapping.get("text")
    if text_col and text_col in df.columns:
        df["text_length"] = df[text_col].fillna("").astype(str).str.len()
        created.append("text_length")

    ts_col = mapping.get("timestamp")
    if ts_col and ts_col in df.columns:
        try:
            ts = pd.to_datetime(df[ts_col], utc=True, errors="coerce")
            df["hour"] = ts.dt.hour
            df["day_of_week"] = ts.dt.dayofweek
            df["date"] = ts.dt.date.astype(str)
            created.extend(["hour", "day_of_week", "date"])
        except Exception:
            pass
    return created


# ---------------------------------------------------------------------------
# Explorer queries (search / sort / filter / paginate)
# ---------------------------------------------------------------------------

def query_rows(
    df: pd.DataFrame,
    mapping: dict,
    *,
    search: str | None = None,
    platform: str | None = None,
    username: str | None = None,
    sentiment: str | None = None,
    classification: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    page: int = 1,
    page_size: int = 50,
) -> dict:
    work = df.copy()

    if search:
        from app.utils.pandas_compat import is_text_series

        needle = str(search).lower()
        mask = pd.Series(False, index=work.index)
        for col in work.columns:
            if is_text_series(work[col]):
                mask |= work[col].fillna("").astype(str).str.lower().str.contains(
                    needle, regex=False
                )
        work = work[mask]

    platform_col = mapping.get("platform")
    if platform and platform_col:
        work = work[work[platform_col].astype(str) == str(platform)]

    user_col = mapping.get("username") or mapping.get("user_id")
    if username and user_col:
        work = work[
            work[user_col].astype(str).str.lower() == str(username).lower()
        ]

    ts_col = mapping.get("timestamp")
    if (date_from or date_to) and ts_col:
        ts = pd.to_datetime(work[ts_col], utc=True, errors="coerce")
        if date_from:
            work = work[ts >= pd.to_datetime(date_from, utc=True, errors="coerce")]
            ts = pd.to_datetime(work[ts_col], utc=True, errors="coerce")
        if date_to:
            work = work[ts <= pd.to_datetime(date_to, utc=True, errors="coerce")]

    if sentiment:
        text_col = mapping.get("text") or mapping.get("text_clean")
        if text_col:
            from app.analysis.sentiment import vader_labels

            labels = vader_labels(work[text_col].fillna("").astype(str).tolist())
            work = work[[l == sentiment for l in labels]]

    if classification and "model_classification" in work.columns:
        work = work[work["model_classification"].astype(str) == str(classification)]

    total_filtered = int(len(work))

    if sort_by and sort_by in work.columns:
        work = work.sort_values(
            by=sort_by, ascending=(str(sort_order).lower() != "desc"), kind="stable"
        )

    total = int(len(work))
    page = max(1, int(page))
    page_size = min(max(1, int(page_size)), 500)
    pages = max(1, (total + page_size - 1) // page_size)
    start = (page - 1) * page_size
    slice_df = work.iloc[start : start + page_size]

    records = []
    for _, row in slice_df.iterrows():
        item = {}
        for key, value in row.items():
            if isinstance(value, (pd.Timestamp, datetime)):
                item[str(key)] = value.isoformat()
            elif pd.isna(value):
                item[str(key)] = None
            elif hasattr(value, "item"):
                item[str(key)] = value.item()
            else:
                item[str(key)] = value if isinstance(value, (int, float, str, bool)) else str(value)
        records.append(item)

    return {
        "items": records,
        "total": total,
        "total_filtered": total_filtered,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "columns": [str(c) for c in work.columns],
    }
