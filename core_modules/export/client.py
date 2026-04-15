from __future__ import annotations

import http.client
import json
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from typing import Any

from core_modules.export.errors import (
    YuqueApiError,
    YuqueAuthError,
    YuqueNetworkError,
    YuqueNotFoundError,
    YuquePermissionError,
    YuqueRateLimitError,
    YuqueValidationError,
)
from core_modules.version import APP_VERSION

BASE_URL = "https://www.yuque.com/api/v2"
DEFAULT_TIMEOUT = 10
USER_AGENT = f"Yuque2Markdown/{APP_VERSION.lstrip('v')}"
RETRYABLE_TRANSPORT_ERRORS = (
    urllib.error.URLError,
    http.client.HTTPException,
    socket.timeout,
    TimeoutError,
    ConnectionError,
    ssl.SSLError,
)


class YuqueClient:
    """封装语雀 OpenAPI 请求、重试与限流状态。"""
    def __init__(
        self,
        token: str,
        timeout: int = DEFAULT_TIMEOUT,
        request_interval: float = 0.1,
        max_retries: int = 5,
        rate_limit_backoff_seconds: float = 5.0,
        network_backoff_seconds: float = 2.0,
        max_backoff_seconds: float = 60.0,
        proxy_host: str | None = None,
        proxy_port: int = 7890,
        proxy_test_url: str = "https://www.baidu.com",
    ) -> None:
        self.token = token
        self.timeout = timeout
        self.request_interval = request_interval
        self.max_retries = max_retries
        self.rate_limit_backoff_seconds = rate_limit_backoff_seconds
        self.network_backoff_seconds = network_backoff_seconds
        self.max_backoff_seconds = max_backoff_seconds
        self.proxy_host = proxy_host.strip() if proxy_host else None
        self.proxy_port = proxy_port
        self.proxy_test_url = proxy_test_url
        self.last_rate_limit: dict[str, str | int | None] = {
            "limit": None,
            "remaining": None,
            "reset": None,
        }
        self._debug_logger = None
        self._opener = self._build_opener()

    def _build_opener(self):
        """构建 urllib opener，支持代理。

        当使用代理时禁用 SSL 证书验证，因为代理软件（如 Clash）可能使用自签名证书。
        """
        if self.proxy_host:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            proxy_url = f"http://{self.proxy_host}:{self.proxy_port}"
            handler = urllib.request.ProxyHandler({
                "http": proxy_url,
                "https": proxy_url,
            })
            https_handler = urllib.request.HTTPSHandler(context=ssl_context)
            return urllib.request.build_opener(handler, https_handler)
        return urllib.request.build_opener()

    def test_proxy(self, test_url: str | None = None) -> tuple[bool, str]:
        """测试代理是否可用，返回 (成功, 消息)。

        使用简单的 HTTP 请求测试代理连通性，不依赖语雀 API。
        注意：代理测试时禁用 SSL 证书验证，因为代理软件可能使用自签名证书。
        """
        if not self.proxy_host:
            return False, "未配置代理"
        url = test_url or self.proxy_test_url
        # 创建不验证 SSL 证书的 context，用于代理测试
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        proxy_url = f"http://{self.proxy_host}:{self.proxy_port}"
        handler = urllib.request.ProxyHandler({
            "http": proxy_url,
            "https": proxy_url,
        })
        https_handler = urllib.request.HTTPSHandler(context=ssl_context)
        opener = urllib.request.build_opener(handler, https_handler)
        try:
            request = urllib.request.Request(
                url=url,
                method="GET",
                headers={"User-Agent": USER_AGENT},
            )
            with opener.open(request, timeout=self.timeout) as response:
                status = response.status if hasattr(response, 'status') else 200
                return True, f"连接成功 ({self.proxy_host}:{self.proxy_port})"
        except urllib.error.URLError as exc:
            return False, str(exc.reason)
        except Exception as exc:
            return False, str(exc)

    def test_direct_connection(self) -> tuple[bool, str]:
        """测试不通过代理的直接连接，用于排查网络问题。"""
        try:
            request = urllib.request.Request(
                url=self.proxy_test_url,
                method="GET",
                headers={"User-Agent": USER_AGENT},
            )
            opener = urllib.request.build_opener()
            with opener.open(request, timeout=self.timeout) as response:
                return True, "直接连接成功"
        except Exception as exc:
            return False, f"直接连接失败: {exc}"

    @property
    def proxy_enabled(self) -> bool:
        """是否启用了代理。"""
        return bool(self.proxy_host)

    def set_debug_logger(self, callback) -> None:
        """设置调试日志回调，用于输出资源请求细节。"""
        self._debug_logger = callback

    def request(self, method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """向语雀 API 发起请求，并处理重试、限流和错误转换。"""
        url = f"{BASE_URL}{path}"
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"

        request = urllib.request.Request(
            url=url,
            method=method,
            headers={
                "X-Auth-Token": self.token,
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
        )

        for attempt in range(self.max_retries):
            if self.request_interval > 0:
                time.sleep(self.request_interval)
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    self._update_rate_limit(response.headers)
                    raw_body = response.read().decode("utf-8")
                    return json.loads(raw_body)
            except urllib.error.HTTPError as exc:
                self._update_rate_limit(exc.headers)
                raw_body = exc.read().decode("utf-8", errors="replace")
                try:
                    payload = json.loads(raw_body)
                except json.JSONDecodeError:
                    payload = {"message": raw_body}
                retry_after = self._parse_retry_after(exc.headers.get("Retry-After"))
                if exc.code == 429 and attempt < self.max_retries - 1:
                    backoff = retry_after or min(self.max_backoff_seconds, self.rate_limit_backoff_seconds * (2 ** attempt))
                    time.sleep(backoff)
                    continue
                self._raise_http_error(exc.code, payload, retry_after=retry_after)
            except RETRYABLE_TRANSPORT_ERRORS as exc:
                if self._retry_transport_error(attempt):
                    continue
                raise YuqueNetworkError(str(exc)) from exc
        raise YuqueNetworkError("请求重试失败")

    def fetch_binary(self, url: str) -> bytes:
        """下载二进制资源内容，并复用重试与限流处理。"""
        binary_url = _prepare_binary_url(url)
        request = urllib.request.Request(
            url=binary_url,
            method="GET",
            headers={
                "X-Auth-Token": self.token,
                "User-Agent": USER_AGENT,
            },
        )
        for attempt in range(self.max_retries):
            if self.request_interval > 0:
                time.sleep(self.request_interval)
            self._debug(f"资源请求开始 [{attempt + 1}/{self.max_retries}] {binary_url}")
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    self._update_rate_limit(response.headers)
                    data = response.read()
                    if _looks_like_html_response(data, response.headers.get("Content-Type")):
                        raise YuqueValidationError(f"附件下载返回了 HTML 页面: {binary_url}")
                    return data
            except urllib.error.HTTPError as exc:
                self._update_rate_limit(exc.headers)
                raw_body = exc.read().decode("utf-8", errors="replace")
                try:
                    payload = json.loads(raw_body)
                except json.JSONDecodeError:
                    payload = {"message": raw_body}
                retry_after = self._parse_retry_after(exc.headers.get("Retry-After"))
                if exc.code == 429 and attempt < self.max_retries - 1:
                    backoff = retry_after or min(self.max_backoff_seconds, self.rate_limit_backoff_seconds * (2 ** attempt))
                    self._debug(
                        f"资源请求限流，准备重试 [{attempt + 2}/{self.max_retries}] {binary_url} | 等待 {backoff:.1f}s"
                    )
                    time.sleep(backoff)
                    continue
                self._raise_http_error(exc.code, payload, retry_after=retry_after)
            except RETRYABLE_TRANSPORT_ERRORS as exc:
                self._debug(
                    f"资源请求异常 [{attempt + 1}/{self.max_retries}] {binary_url} | {exc.__class__.__name__}: {exc}"
                )
                if self._retry_transport_error(attempt):
                    continue
                raise YuqueNetworkError(str(exc)) from exc
        raise YuqueNetworkError("资源下载重试失败")

    def _retry_transport_error(self, attempt: int) -> bool:
        """对代理或连接层瞬时异常执行统一重试，并重新创建 opener，避免复用已失效的连接对象。"""
        if attempt >= self.max_retries - 1:
            return False
        self._opener = self._build_opener()
        time.sleep(min(self.max_backoff_seconds, self.network_backoff_seconds * (2 ** attempt)))
        return True

    def _debug(self, message: str) -> None:
        if self._debug_logger is not None:
            self._debug_logger(message)

    def _update_rate_limit(self, headers) -> None:
        """从响应头中提取并缓存最新的限流信息。"""
        if headers is None:
            return
        limit = headers.get("X-RateLimit-Limit")
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")
        self.last_rate_limit = {
            "limit": int(limit) if limit and str(limit).isdigit() else None,
            "remaining": int(remaining) if remaining and str(remaining).isdigit() else None,
            "reset": reset,
        }

    def _raise_http_error(self, status: int, payload: dict[str, Any], retry_after: float | None = None) -> None:
        message = payload.get("message") or payload.get("error") or f"HTTP {status}"
        if status == 401:
            raise YuqueAuthError(message, status=status, payload=payload)
        if status == 403:
            raise YuquePermissionError(message, status=status, payload=payload)
        if status == 404:
            raise YuqueNotFoundError(message, status=status, payload=payload)
        if status == 422:
            raise YuqueValidationError(message, status=status, payload=payload)
        if status == 429:
            raise YuqueRateLimitError(message, status=status, payload=payload, retry_after=retry_after)
        raise YuqueApiError(message, status=status, payload=payload)

    def _parse_retry_after(self, value: str | None) -> float | None:
        if not value:
            return None
        raw = value.strip()
        try:
            return max(0.0, min(self.max_backoff_seconds, float(raw)))
        except ValueError:
            pass
        try:
            retry_at = parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            return None
        delay = retry_at.timestamp() - time.time()
        return max(0.0, min(self.max_backoff_seconds, delay))

    def get_current_user(self) -> dict[str, Any]:
        return self.request("GET", "/user")

    def get_repo_detail(self, group_login: str, book_slug: str) -> dict[str, Any]:
        return self.request("GET", f"/repos/{urllib.parse.quote(group_login)}/{urllib.parse.quote(book_slug)}")

    def get_repo_toc(self, group_login: str, book_slug: str) -> dict[str, Any]:
        return self.request("GET", f"/repos/{urllib.parse.quote(group_login)}/{urllib.parse.quote(book_slug)}/toc")

    def get_repo_toc_tree(self, group_login: str, book_slug: str) -> list[dict[str, Any]]:
        payload = self.get_repo_toc(group_login, book_slug)
        data = payload.get("data", [])
        if isinstance(data, list):
            return data
        return []

    def get_repo_docs_page(self, group_login: str, book_slug: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/repos/{urllib.parse.quote(group_login)}/{urllib.parse.quote(book_slug)}/docs",
            {"limit": limit, "offset": offset},
        )

    def get_all_repo_docs(self, group_login: str, book_slug: str, limit: int = 100) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        offset = 0
        while True:
            payload = self.get_repo_docs_page(group_login, book_slug, limit=limit, offset=offset)
            page_items = extract_data_list(payload)
            docs.extend(page_items)
            if len(page_items) < limit:
                break
            offset += limit
        return docs

    def get_doc_detail(self, group_login: str, book_slug: str, doc_id_or_slug: str) -> dict[str, Any]:
        return self.request(
            "GET",
            f"/repos/{urllib.parse.quote(group_login)}/{urllib.parse.quote(book_slug)}/docs/{urllib.parse.quote(str(doc_id_or_slug))}",
        )


def extract_data_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("data", [])
    if isinstance(items, list):
        return items
    return []


def _prepare_binary_url(url: str) -> str:
    """为语雀附件 URL 补充下载参数，避免拿到预览页 HTML。"""
    parsed = urllib.parse.urlparse(url)
    if "yuque.com" not in parsed.netloc.lower():
        return url
    if "/attachments/" not in parsed.path.lower():
        return url
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query_dict = {key: value for key, value in query}
    query_dict.setdefault("download", "1")
    new_query = urllib.parse.urlencode(query_dict)
    return parsed._replace(query=new_query).geturl()


def _looks_like_html_response(data: bytes, content_type: str | None) -> bool:
    """检测错误下载到的 HTML 页面，避免将其当作附件写盘。"""
    content_type = (content_type or "").lower()
    if "text/html" in content_type:
        return True
    prefix = data[:256].lstrip().lower()
    return prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html")
