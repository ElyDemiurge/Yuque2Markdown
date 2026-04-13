class YuqueError(Exception):
    """Base error for Yuque exporter."""


class YuqueApiError(YuqueError):
    def __init__(self, message: str, status: int | None = None, payload: dict | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.payload = payload or {}


class YuqueRetryableError(YuqueError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class YuqueAuthError(YuqueApiError):
    """Authentication failed."""


class YuquePermissionError(YuqueApiError):
    """Permission denied."""


class YuqueNotFoundError(YuqueApiError):
    """Entity not found."""


class YuqueRateLimitError(YuqueApiError):
    def __init__(self, message: str, status: int | None = None, payload: dict | None = None, retry_after: float | None = None) -> None:
        super().__init__(message, status=status, payload=payload)
        self.retry_after = retry_after


class YuqueValidationError(YuqueApiError):
    """Invalid request or user input."""


class YuqueNetworkError(YuqueRetryableError):
    """Network level failure."""


class ExportError(YuqueError):
    """Export level failure."""
