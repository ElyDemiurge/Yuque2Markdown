class YuqueError(Exception):
    """语雀导出相关异常的基类。"""


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
    """鉴权失败。"""


class YuquePermissionError(YuqueApiError):
    """权限不足。"""


class YuqueNotFoundError(YuqueApiError):
    """目标资源不存在。"""


class YuqueRateLimitError(YuqueApiError):
    def __init__(self, message: str, status: int | None = None, payload: dict | None = None, retry_after: float | None = None) -> None:
        super().__init__(message, status=status, payload=payload)
        self.retry_after = retry_after


class YuqueValidationError(YuqueApiError):
    """请求参数或用户输入不合法。"""


class YuqueNetworkError(YuqueRetryableError):
    """网络层异常。"""


class ExportError(YuqueError):
    """导出流程异常。"""
