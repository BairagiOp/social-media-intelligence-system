"""Process-wide application state (bootstrap status + analysis cache)."""
from __future__ import annotations

import threading
from datetime import datetime, timezone


class BootstrapState:
    def __init__(self):
        self.lock = threading.Lock()
        self.status = "PENDING"      # PENDING | RUNNING | READY | DEGRADED
        self.steps: list[dict] = []
        self.error: str | None = None

    def step(self, name: str, status: str, detail: str = "") -> None:
        with self.lock:
            self.steps.append(
                {
                    "name": name,
                    "status": status,
                    "detail": detail,
                    "at": datetime.now(timezone.utc).isoformat(),
                }
            )
            if status == "RUNNING":
                self.status = "RUNNING"
            elif status == "ERROR":
                self.status = "DEGRADED"
                self.error = detail
            elif status == "DONE" and self.status in {"PENDING", "RUNNING"}:
                self.status = "READY"

    def to_dict(self) -> dict:
        with self.lock:
            return {
                "status": self.status,
                "steps": list(self.steps),
                "error": self.error,
            }


class AnalysisCache:
    """Keeps the most recent analysis result per dataset for dashboard reuse."""

    def __init__(self):
        self.lock = threading.Lock()
        self._store: dict[tuple[str, str], dict] = {}

    def store(self, dataset_id: str, kind: str, payload: dict) -> None:
        with self.lock:
            self._store[(dataset_id, kind)] = payload

    def get(self, dataset_id: str, kind: str) -> dict | None:
        with self.lock:
            return self._store.get((dataset_id, kind))


bootstrap_state = BootstrapState()
analysis_cache = AnalysisCache()
