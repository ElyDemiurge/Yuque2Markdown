"""语雀客户端实现。

本模块封装 OpenAPI 与网页端接口请求、代理支持、重试、限流与资源下载逻辑。
"""

from __future__ import annotations

import http.client
import json
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from typing import Any

from core_modules.export.errors import (
    YuqueApiError,
    YuqueAuthError,
    ExportCancelledError,
    YuqueNetworkError,
    YuqueNotFoundError,
    YuquePermissionError,
    YuqueRateLimitError,
    YuqueValidationError,
)
from core_modules.version import APP_VERSION

API_BASE_URL = "https://www.yuque.com/api/v2"
WEB_BASE_URL = "https://www.yuque.com/api"
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
        token: str = "",
        *,
        cookie: str = "",
        auth_mode: str = "token",
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
        """初始化语雀客户端。"""
        self.token = token
        self.cookie = cookie.strip()
        self.auth_mode = auth_mode if auth_mode in {"token", "cookie"} else "token"
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
        self._web_book_cache: dict[tuple[str, str], dict[str, Any]] = {}
        self._debug_logger = None
        self._opener = self._build_opener()
        self._cancel_event: threading.Event | None = None

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

    def _auth_headers(self) -> dict[str, str]:
        """根据当前认证方式构造请求头。"""
        if self.auth_mode == "cookie":
            return {"Cookie": self.cookie}
        return {"X-Auth-Token": self.token}

    def set_cancel_event(self, cancel_event: threading.Event | None) -> None:
        """设置导出取消事件。"""
        self._cancel_event = cancel_event

    def _check_cancel(self) -> None:
        """在耗时操作前检查是否已请求取消。"""
        if self._cancel_event is not None and self._cancel_event.is_set():
            raise ExportCancelledError("用户中止导出")

    def _sleep_with_cancel(self, seconds: float) -> None:
        """在可取消前提下等待指定秒数。"""
        deadline = time.monotonic() + max(0.0, seconds)
        while True:
            self._check_cancel()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            time.sleep(min(0.1, remaining))

    def web_request(self, method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """向语雀网页端 API 发起请求，供 Cookie 登录使用。"""
        url = f"{WEB_BASE_URL}{path}"
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"
        request = urllib.request.Request(
            url=url,
            method=method,
            headers={
                "Accept": "application/json, text/plain, */*",
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://www.yuque.com/",
                **self._auth_headers(),
            },
        )
        for attempt in range(self.max_retries):
            self._check_cancel()
            if self.request_interval > 0:
                self._sleep_with_cancel(self.request_interval)
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
                    self._sleep_with_cancel(backoff)
                    continue
                self._raise_http_error(exc.code, payload, retry_after=retry_after)
            except RETRYABLE_TRANSPORT_ERRORS as exc:
                if self._retry_transport_error(attempt):
                    continue
                raise YuqueNetworkError(str(exc)) from exc
        raise YuqueNetworkError("网页端请求重试失败")

    def request(self, method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """向语雀 API 发起请求，并处理重试、限流和错误转换。"""
        url = f"{API_BASE_URL}{path}"
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}"

        request = urllib.request.Request(
            url=url,
            method=method,
            headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
                **self._auth_headers(),
            },
        )

        for attempt in range(self.max_retries):
            self._check_cancel()
            if self.request_interval > 0:
                self._sleep_with_cancel(self.request_interval)
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
                    self._sleep_with_cancel(backoff)
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
                "User-Agent": USER_AGENT,
                "Accept": "*/*",
                "Referer": "https://www.yuque.com/",
                **self._auth_headers(),
            },
        )
        for attempt in range(self.max_retries):
            self._check_cancel()
            if self.request_interval > 0:
                self._sleep_with_cancel(self.request_interval)
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
                    self._sleep_with_cancel(backoff)
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
        self._sleep_with_cancel(min(self.max_backoff_seconds, self.network_backoff_seconds * (2 ** attempt)))
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
        """把 HTTP 状态码转换为更具体的领域异常。"""
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
        """解析 ``Retry-After`` 响应头。

        说明:
            该字段既可能是秒数，也可能是 HTTP 日期，因此这里按两种格式依次解析。
        """
        if not value:
            return None
        raw = value.strip()
        try:
            return max(0.0, min(self.max_backoff_seconds, float(raw)))
        except ValueError:
            # 不是纯秒数时，继续按 HTTP 日期格式解析。
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
        """获取当前登录用户信息。"""
        if self.auth_mode == "cookie":
            return self.web_request("GET", "/mine")
        return self.request("GET", "/user")

    def get_repo_detail(self, group_login: str, book_slug: str) -> dict[str, Any]:
        """获取知识库详情。"""
        if self.auth_mode == "cookie":
            book = self._find_web_book(group_login, book_slug)
            return {"data": book}
        return self.request("GET", f"/repos/{urllib.parse.quote(group_login)}/{urllib.parse.quote(book_slug)}")

    def get_repo_toc(self, group_login: str, book_slug: str) -> dict[str, Any]:
        """获取知识库目录。"""
        if self.auth_mode == "cookie":
            book = self._find_web_book(group_login, book_slug)
            return self.web_request("GET", "/catalog_nodes", {"book_id": book.get("id")})
        return self.request("GET", f"/repos/{urllib.parse.quote(group_login)}/{urllib.parse.quote(book_slug)}/toc")

    def get_repo_toc_tree(self, group_login: str, book_slug: str) -> list[dict[str, Any]]:
        """获取知识库目录树原始数据。"""
        payload = self.get_repo_toc(group_login, book_slug)
        data = payload.get("data", [])
        if isinstance(data, list):
            return data
        return []

    def get_repo_docs_page(self, group_login: str, book_slug: str, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        """按页获取知识库文档列表。"""
        if self.auth_mode == "cookie":
            book = self._find_web_book(group_login, book_slug)
            return self.web_request("GET", "/docs", {"book_id": book.get("id"), "limit": limit, "offset": offset})
        return self.request(
            "GET",
            f"/repos/{urllib.parse.quote(group_login)}/{urllib.parse.quote(book_slug)}/docs",
            {"limit": limit, "offset": offset},
        )

    def get_all_repo_docs(self, group_login: str, book_slug: str, limit: int = 100) -> list[dict[str, Any]]:
        """获取知识库下全部文档元数据。"""
        docs: list[dict[str, Any]] = []
        offset = 0
        while True:
            self._check_cancel()
            payload = self.get_repo_docs_page(group_login, book_slug, limit=limit, offset=offset)
            page_items = extract_data_list(payload)
            docs.extend(page_items)
            if len(page_items) < limit:
                break
            offset += limit
        return docs

    def get_doc_detail(self, group_login: str, book_slug: str, doc_id_or_slug: str) -> dict[str, Any]:
        """获取单篇文档详情。"""
        if self.auth_mode == "cookie":
            book = self._find_web_book(group_login, book_slug)
            payload = self.web_request("GET", f"/docs/{urllib.parse.quote(str(doc_id_or_slug))}", {"book_id": book.get("id")})
            data = dict(payload.get("data", {}))
            if "content" in data and "body_lake" not in data:
                data["body_lake"] = data.get("content") or ""
            return {"data": data}
        return self.request(
            "GET",
            f"/repos/{urllib.parse.quote(group_login)}/{urllib.parse.quote(book_slug)}/docs/{urllib.parse.quote(str(doc_id_or_slug))}",
        )

    def get_web_books(self) -> list[dict[str, Any]]:
        """读取网页端“我的知识库”列表。"""
        payload = self.web_request("GET", "/mine/books")
        books = payload.get("data", [])
        if not isinstance(books, list):
            return []
        return [_normalize_web_book(book) for book in books if isinstance(book, dict)]

    def _find_web_book(self, group_login: str, book_slug: str) -> dict[str, Any]:
        """在网页端知识库列表中定位指定知识库。"""
        key = (group_login, book_slug)
        if key in self._web_book_cache:
            return self._web_book_cache[key]
        for book in self.get_web_books():
            if book.get("namespace") == f"{group_login}/{book_slug}" or (
                book.get("slug") == book_slug and (book.get("user") or {}).get("login") == group_login
            ):
                self._web_book_cache[key] = book
                return book
        raise YuqueNotFoundError(f"未找到知识库 {group_login}/{book_slug}")


def extract_data_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """从标准接口响应中提取 ``data`` 列表。"""
    items = payload.get("data", [])
    if isinstance(items, list):
        return items
    return []


def _normalize_web_book(book: dict[str, Any]) -> dict[str, Any]:
    """把网页端知识库对象补齐为更接近 OpenAPI 的结构。"""
    user = book.get("user") or {}
    login = user.get("login") or ""
    slug = book.get("slug") or ""
    normalized = dict(book)
    if login and slug:
        normalized["namespace"] = f"{login}/{slug}"
    normalized["book_slug"] = slug
    return normalized


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
