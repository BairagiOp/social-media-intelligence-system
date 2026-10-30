"""Load dataset files (CSV/JSON/JSONL/Parquet) into pandas DataFrames."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.utils.errors import ValidationFailed

MAX_PREVIEW_ROWS = 500_000


def load_dataframe(path: str | Path, fmt: str | None = None) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise ValidationFailed("Dataset file not found on server storage.")
    fmt = (fmt or path.suffix.lstrip(".")).lower()
    try:
        if fmt == "csv":
            df = pd.read_csv(path)
        elif fmt == "parquet":
            df = pd.read_parquet(path)
        elif fmt == "json":
            df = _read_json(path)
        elif fmt == "jsonl":
            df = pd.read_json(path, lines=True)
        else:
            raise ValidationFailed(f"Unsupported dataset format '{fmt}'.")
    except ValidationFailed:
        raise
    except Exception as exc:
        raise ValidationFailed(f"Could not parse {fmt.upper()} file: {exc}") from exc

    if df is None or df.empty:
        raise ValidationFailed("Dataset contains no records.")
    if len(df) > MAX_PREVIEW_ROWS:
        df = df.head(MAX_PREVIEW_ROWS)
    # Flatten list/dict cells so downstream processing never chokes.
    from app.utils.pandas_compat import is_text_series

    for col in df.columns:
        if df[col].dtype == object or is_text_series(df[col]):
            sample = df[col].dropna().head(20)
            if any(isinstance(v, (list, dict)) for v in sample):
                df[col] = df[col].apply(
                    lambda v: json.dumps(v, ensure_ascii=False)
                    if isinstance(v, (list, dict))
                    else v
                )
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _read_json(path: Path) -> pd.DataFrame:
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, dict):
        for key in ("data", "records", "rows", "items"):
            if key in payload and isinstance(payload[key], list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    if not isinstance(payload, list):
        raise ValidationFailed("JSON must contain a list of records.")
    return pd.DataFrame(payload)
