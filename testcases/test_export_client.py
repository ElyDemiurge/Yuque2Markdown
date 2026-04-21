"""语雀客户端传输重试测试。"""

from __future__ import annotations

import http.client
import threading
import urllib.error

from core_modules.export.client import YuqueClient
from core_modules.export.errors import ExportCancelledError, YuqueNetworkError, YuqueRateLimitError


class _FakeResponse:
    def __init__(self, data: bytes, headers: dict[str, str] | None = None) -> None:
        self._data = data
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def read(self) -> bytes:
        return self._data


class _FakeOpener:
    def __init__(self, result) -> None:
        self.result = result

    def open(self, request, timeout=None):
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class _RetryingClient(YuqueClient):
    def __init__(self, opener_results: list[object]) -> None:
        self._opener_results = list(opener_results)
        self.build_count = 0
        super().__init__(
            token="demo-token",
            request_interval=0,
            max_retries=len(opener_results),
            network_backoff_seconds=0,
            max_backoff_seconds=0,
        )

    def _build_opener(self):
        self.build_count += 1
        if not self._opener_results:
            raise AssertionError("unexpected opener rebuild")
        return _FakeOpener(self._opener_results.pop(0))


def test_fetch_binary_retries_on_http2_bad_status_line() -> None:
    client = _RetryingClient(
        [
            http.client.BadStatusLine("HTTP/2"),
            _FakeResponse(b"image-bytes", {"Content-Type": "image/png"}),
        ]
    )

    data = client.fetch_binary("https://cdn.nlark.com/demo.png")

    assert data == b"image-bytes"
    assert client.build_count == 2


def test_request_retries_on_http2_bad_status_line() -> None:
    client = _RetryingClient(
        [
            http.client.BadStatusLine("HTTP/2"),
            _FakeResponse(b'{"data":{"id":1}}', {"Content-Type": "application/json"}),
        ]
    )

    payload = client.request("GET", "/user")

    assert payload == {"data": {"id": 1}}
    assert client.build_count == 2


def test_web_request_retries_on_http2_bad_status_line() -> None:
    client = _RetryingClient(
        [
            http.client.BadStatusLine("HTTP/2"),
            _FakeResponse(b'{"data":{"id":1}}', {"Content-Type": "application/json"}),
        ]
    )

    payload = client.web_request("GET", "/mine")

    assert payload == {"data": {"id": 1}}
    assert client.build_count == 2


def test_web_request_raises_rate_limit_error() -> None:
    error = urllib.error.HTTPError(
        "https://www.yuque.com/api/mine",
        429,
        "Too Many Requests",
        {"Retry-After": "1"},
        None,
    )
    error.read = lambda: b'{"message":"rate limited"}'
    client = _RetryingClient([error])

    try:
        client.web_request("GET", "/mine")
    except YuqueRateLimitError as exc:
        assert "rate limited" in str(exc)
    else:
        raise AssertionError("expected YuqueRateLimitError")


def test_web_request_raises_network_error_after_retries() -> None:
    client = _RetryingClient([http.client.BadStatusLine("HTTP/2")])

    try:
        client.web_request("GET", "/mine")
    except YuqueNetworkError:
        pass
    else:
        raise AssertionError("expected YuqueNetworkError")


def test_request_raises_cancelled_before_network_call() -> None:
    client = _RetryingClient([_FakeResponse(b'{"data":{"id":1}}', {"Content-Type": "application/json"})])
    cancel_event = threading.Event()
    cancel_event.set()
    client.set_cancel_event(cancel_event)

    try:
        client.request("GET", "/user")
    except ExportCancelledError as exc:
        assert "用户中止导出" in str(exc)
    else:
        raise AssertionError("expected ExportCancelledError")
