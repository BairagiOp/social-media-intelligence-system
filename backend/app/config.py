"""Environment-driven application settings.

All configuration comes from environment variables (see .env.example).
No secrets are hard-coded.
"""
from __future__ import annotations

import os
from pathlib import Path

try:  # optional .env loading
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional
    pass

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent


def _env(key: str, default: str) -> str:
    value = os.getenv(key)
    return value if value not in (None, "") else default


def _env_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Runtime settings resolved from environment variables."""

    def __init__(self) -> None:
        self.env: str = _env("SMDPIS_ENV", "development")
        self.log_level: str = _env("SMDPIS_LOG_LEVEL", "INFO")
        self.secret_key: str = _env("SMDPIS_SECRET_KEY", "dev-insecure-secret-change-me")
        self.auto_bootstrap: bool = _env_bool("SMDPIS_AUTO_BOOTSTRAP", True)
        self.cors_origins: list[str] = [
            o.strip()
            for o in _env(
                "SMDPIS_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173",
            ).split(",")
            if o.strip()
        ]
        self.database_url: str = _env(
            "SMDPIS_DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'data' / 'smdpis.db'}"
        )
        self.max_upload_mb: int = int(_env("SMDPIS_MAX_UPLOAD_MB", "50"))
        self.allowed_extensions: set[str] = {
            e.strip().lower()
            for e in _env("SMDPIS_ALLOWED_EXTENSIONS", "csv,json,jsonl,parquet").split(",")
            if e.strip()
        }

        data_dir = Path(_env("SMDPIS_DATA_DIR", str(PROJECT_ROOT / "data")))
        if not data_dir.is_absolute():
            data_dir = (PROJECT_ROOT / data_dir).resolve()
        self.data_dir: Path = data_dir
        self.raw_dir: Path = data_dir / "raw"
        self.processed_dir: Path = data_dir / "processed"
        self.sample_dir: Path = data_dir / "sample"
        self.evidence_dir: Path = data_dir / "evidence"

        model_dir = Path(_env("SMDPIS_MODEL_DIR", str(BACKEND_DIR / "models")))
        if not model_dir.is_absolute():
            model_dir = (PROJECT_ROOT / model_dir).resolve()
        self.model_dir: Path = model_dir

        self.catalog_path: Path = BACKEND_DIR / "datasets" / "dataset_catalog.json"
        self.app_version: str = "1.0.0"

        # --- Web collection (fetch / platform sources / crawl) -------------
        # SMDPIS only ever contacts PUBLIC sources that permit automated access.
        # Outbound requests are guarded: http(s) only, no URL credentials, every
        # DNS answer (including after each redirect) must be a public address,
        # optional host allow-list, size/timeout caps, and robots.txt honoured.
        self.fetch_enabled: bool = _env_bool("SMDPIS_FETCH_ENABLED", True)
        self.user_agent: str = _env(
            "SMDPIS_USER_AGENT", "SMDPIS/1.0 (+public-data-collection; authorized-use)"
        )
        self.fetch_timeout: float = float(_env("SMDPIS_FETCH_TIMEOUT", "20"))
        self.fetch_max_mb: int = int(_env("SMDPIS_FETCH_MAX_MB", str(self.max_upload_mb)))
        self.fetch_max_redirects: int = int(_env("SMDPIS_FETCH_MAX_REDIRECTS", "5"))
        self.fetch_min_interval: float = float(_env("SMDPIS_FETCH_MIN_INTERVAL", "1.0"))
        self.fetch_allow_private: bool = _env_bool("SMDPIS_FETCH_ALLOW_PRIVATE", False)
        self.fetch_robots_obey: bool = _env_bool("SMDPIS_ROBOTS_OBEY", True)
        self.fetch_host_allowlist: set[str] = {
            h.strip().lower()
            for h in _env("SMDPIS_FETCH_HOST_ALLOWLIST", "").split(",")
            if h.strip()
        }

        self.crawl_max_pages: int = int(_env("SMDPIS_CRAWL_MAX_PAGES", "10"))
        self.crawl_max_depth: int = int(_env("SMDPIS_CRAWL_MAX_DEPTH", "2"))
        self.collect_max_items: int = int(_env("SMDPIS_COLLECT_MAX_ITEMS", "500"))

    def ensure_dirs(self) -> None:
        for path in (
            self.data_dir,
            self.raw_dir,
            self.processed_dir,
            self.sample_dir,
            self.evidence_dir,
            self.model_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
        for task in ("sentiment", "bot_detection", "misinformation", "topic_model"):
            (self.model_dir / task).mkdir(parents=True, exist_ok=True)


settings = Settings()
