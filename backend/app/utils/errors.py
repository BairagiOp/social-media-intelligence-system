"""Shared error types and API error helpers."""
from __future__ import annotations


class APIError(Exception):
    """Application error carrying an HTTP status and a user-safe message."""

    def __init__(self, status_code: int, message: str, code: str = "error"):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code


class NotFoundError(APIError):
    def __init__(self, message: str = "Resource not found."):
        super().__init__(404, message, "not_found")


class ValidationFailed(APIError):
    def __init__(self, message: str):
        super().__init__(422, message, "validation_failed")


class TrainingError(APIError):
    def __init__(self, message: str):
        super().__init__(422, message, "training_failed")


class FetchFailed(APIError):
    """An outbound collection request failed (network, policy or remote error)."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(status_code, message, "fetch_failed")


class ModelNotTrained(APIError):
    def __init__(self, task: str):
        super().__init__(
            409,
            f"Model not trained for task '{task}'. Train and activate a model first.",
            "model_not_trained",
        )
