from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from core_modules.export.client import DEFAULT_TIMEOUT, YuqueClient
from core_modules.export.errors import YuqueAuthError, YuqueNetworkError, YuquePermissionError, YuqueRateLimitError
from core_modules.export.exporter import Exporter
from core_modules.export.models import ExportOptions, ExportResult, ProgressSnapshot, RepoRef, TocNode
from core_modules.export.progress import ExportProgressUI
from core_modules.export.resolver import resolve_repo_input
from core_modules.export.toc_builder import build_toc_tree


def build_client(
    token: str,
    *,
    request_interval: float,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = 5,
    rate_limit_backoff_seconds: float = 5.0,
    network_backoff_seconds: float = 2.0,
    max_backoff_seconds: float = 60.0,
    proxy_host: str | None = None,
    proxy_port: int = 7890,
    proxy_test_url: str = "https://www.baidu.com",
) -> YuqueClient:
    return YuqueClient(
        token=token,
        request_interval=request_interval,
        timeout=timeout,
        max_retries=max_retries,
        rate_limit_backoff_seconds=rate_limit_backoff_seconds,
        network_backoff_seconds=network_backoff_seconds,
        max_backoff_seconds=max_backoff_seconds,
        proxy_host=proxy_host,
        proxy_port=proxy_port,
        proxy_test_url=proxy_test_url,
    )


def fetch_repo_toc(client: YuqueClient, repo_input: str) -> tuple[RepoRef, list[TocNode]]:
    repo = resolve_repo_input(repo_input)
    raw_toc = client.get_repo_toc_tree(repo.group_login, repo.book_slug)
    return repo, build_toc_tree(raw_toc)


def execute_export(
    client: YuqueClient,
    options: ExportOptions,
    *,
    progress_callback: Callable[[ProgressSnapshot], None] | None = None,
) -> ExportResult:
    repo = resolve_repo_input(options.repo_input)
    exporter = Exporter(client, progress_callback=progress_callback)
    return exporter.export_repo(repo, options)


def handle_export_error(exc: Exception) -> tuple[int, str]:
    if isinstance(exc, YuqueAuthError):
        return 1, f"认证失败: {exc}"
    if isinstance(exc, YuquePermissionError):
        return 1, f"无权限访问该知识库: {exc}"
    if isinstance(exc, YuqueRateLimitError):
        wait_hint = f"，建议至少等待 {int(exc.retry_after)} 秒后重试" if getattr(exc, "retry_after", None) else "，请稍后重试"
        return 2, f"触发语雀限流: {exc}{wait_hint}"
    if isinstance(exc, YuqueNetworkError):
        return 1, f"网络请求失败: {exc}"
    return 1, str(exc)


def list_accessible_repos(client: YuqueClient) -> tuple[dict, list[dict]]:
    user_payload = client.get_current_user()
    user = user_payload.get("data", {})
    login = user.get("login")
    if not login:
        raise ValueError("无法获取当前用户 login")
    repos = client.request("GET", f"/users/{login}/repos", {"limit": 100, "offset": 0}).get("data", [])
    return user, repos
