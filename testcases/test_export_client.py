"""Tests for Yuque client transport retry behavior."""

from __future__ import annotations

import http.client

from core_modules.export.client import YuqueClient


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
