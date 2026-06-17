"""Yuque2Markdown 配置校验模块。

本模块对所有配置字段进行校验。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from core_modules.config.models import AppConfig, ExportDefaultsConfig, ProxyConfig


MIN_TIMEOUT = 1
MAX_TIMEOUT = 300
MIN_TOKEN_CHECK_TIMEOUT = 1
MAX_TOKEN_CHECK_TIMEOUT = 60
MIN_RETRIES = 0
MAX_RETRIES = 20
MIN_BACKOFF = 0.0
MAX_RATE_LIMIT_BACKOFF = 300.0
MAX_NETWORK_BACKOFF = 60.0
MIN_MAX_BACKOFF = 5.0
MAX_MAX_BACKOFF = 600.0
MIN_MAX_DOCS = 1
MAX_MAX_DOCS = 10000
MAX_REQUEST_INTERVAL = 60.0
MIN_PORT = 1
MAX_PORT = 65535
MAX_NAME_LENGTH = 255
HTTPS_URL_PATTERN = re.compile(r"^https://", re.IGNORECASE)
SLUG_PATTERN = re.compile(r"^[a-z0-9_-]+$", re.IGNORECASE)
ATTACHMENT_SUFFIX_PATTERN = re.compile(r"^\.[a-z0-9][a-z0-9._+-]*$", re.IGNORECASE)


@dataclass(slots=True)
class ValidationError:
    """单个校验错误，包含字段名和错误信息。"""
    field: str
    message: str

    def __str__(self) -> str:
        return f"{self.field}: {self.message}"


def validate_config(config: AppConfig) -> list[ValidationError]:
    """校验整个应用程序配置。"""
    errors: list[ValidationError] = []

    if config.version < 1:
        errors.append(ValidationError("version", "配置版本号必须 >= 1"))

    if config.auth_mode not in {"token", "cookie"}:
        errors.append(ValidationError("auth_mode", "登录方式必须是 token 或 cookie"))

    token = config.token
    if token and len(token) < 10:
        errors.append(ValidationError("token", "Token 长度过短，可能无效"))

    if config.cookie and "=" not in config.cookie:
        errors.append(ValidationError("cookie", "Cookie 格式无效，应包含 name=value"))

    if config.last_repo_input:
        if not _is_valid_repo_input(config.last_repo_input):
            errors.append(ValidationError("last_repo_input", "知识库路径格式无效，应为 group_login/book_slug"))

    errors.extend(validate_export_defaults(config.export_defaults))

    return errors


def validate_export_defaults(defaults: ExportDefaultsConfig) -> list[ValidationError]:
    """校验导出默认配置。"""
    errors: list[ValidationError] = []

    if not defaults.output_dir:
        errors.append(ValidationError("output_dir", "输出目录不能为空"))
    elif len(defaults.output_dir) > MAX_NAME_LENGTH:
        errors.append(ValidationError("output_dir", f"输出目录名称过长（最大 {MAX_NAME_LENGTH} 字符）"))
    elif _has_invalid_path_chars(defaults.output_dir):
        errors.append(ValidationError("output_dir", "输出目录包含无效字符"))
    elif ".." in defaults.output_dir:
        errors.append(ValidationError("output_dir", "输出目录不能包含路径遍历符 (..)"))

    if defaults.request_interval < MIN_BACKOFF or defaults.request_interval > MAX_REQUEST_INTERVAL:
        errors.append(ValidationError("request_interval", f"请求间隔必须在 {MIN_BACKOFF} - {MAX_REQUEST_INTERVAL} 秒之间"))

    if defaults.timeout < MIN_TIMEOUT or defaults.timeout > MAX_TIMEOUT:
        errors.append(ValidationError("timeout", f"超时时间必须在 {MIN_TIMEOUT} - {MAX_TIMEOUT} 秒之间"))

    if defaults.token_check_timeout < MIN_TOKEN_CHECK_TIMEOUT or defaults.token_check_timeout > MAX_TOKEN_CHECK_TIMEOUT:
        errors.append(ValidationError("token_check_timeout", f"Token 检查超时必须在 {MIN_TOKEN_CHECK_TIMEOUT} - {MAX_TOKEN_CHECK_TIMEOUT} 秒之间"))

    if defaults.request_max_retries < MIN_RETRIES or defaults.request_max_retries > MAX_RETRIES:
        errors.append(ValidationError("request_max_retries", f"重试次数必须在 {MIN_RETRIES} - {MAX_RETRIES} 之间"))

    if defaults.rate_limit_backoff_seconds < MIN_BACKOFF or defaults.rate_limit_backoff_seconds > MAX_RATE_LIMIT_BACKOFF:
        errors.append(ValidationError("rate_limit_backoff_seconds", f"限流等待必须在 {MIN_BACKOFF} - {MAX_RATE_LIMIT_BACKOFF} 秒之间"))

    if defaults.network_backoff_seconds < MIN_BACKOFF or defaults.network_backoff_seconds > MAX_NETWORK_BACKOFF:
        errors.append(ValidationError("network_backoff_seconds", f"网络等待必须在 {MIN_BACKOFF} - {MAX_NETWORK_BACKOFF} 秒之间"))

    if defaults.max_backoff_seconds < MIN_MAX_BACKOFF or defaults.max_backoff_seconds > MAX_MAX_BACKOFF:
        errors.append(ValidationError("max_backoff_seconds", f"最大等待必须在 {MIN_MAX_BACKOFF} - {MAX_MAX_BACKOFF} 秒之间"))

    if defaults.max_backoff_seconds < defaults.rate_limit_backoff_seconds:
        errors.append(ValidationError("max_backoff_seconds", "单次重试等待上限应 >= 触发限流后的首次等待时间"))
    if defaults.max_backoff_seconds < defaults.network_backoff_seconds:
        errors.append(ValidationError("max_backoff_seconds", "单次重试等待上限应 >= 网络错误后的首次等待时间"))

    if defaults.max_docs is not None:
        if defaults.max_docs < MIN_MAX_DOCS or defaults.max_docs > MAX_MAX_DOCS:
            errors.append(ValidationError("max_docs", f"最大文档数必须在 {MIN_MAX_DOCS} - {MAX_MAX_DOCS} 之间"))

    if not defaults.assets_dir_name:
        errors.append(ValidationError("assets_dir_name", "资源目录名不能为空"))
    elif defaults.assets_dir_name != defaults.assets_dir_name.strip():
        errors.append(ValidationError("assets_dir_name", "资源目录名不能包含前后空格"))
    elif _has_invalid_path_chars(defaults.assets_dir_name):
        errors.append(ValidationError("assets_dir_name", "资源目录名包含无效字符"))
    elif "/" in defaults.assets_dir_name or "\\" in defaults.assets_dir_name:
        errors.append(ValidationError("assets_dir_name", "资源目录名不能包含路径分隔符"))

    for suffix in defaults.attachment_suffixes:
        if suffix == "*":
            continue
        if not ATTACHMENT_SUFFIX_PATTERN.match(suffix):
            errors.append(ValidationError("attachment_suffixes", f"附件扩展名格式无效: {suffix}"))

    errors.extend(validate_proxy(defaults.proxy))

    return errors


def validate_proxy(proxy: ProxyConfig) -> list[ValidationError]:
    """校验代理配置。"""
    errors: list[ValidationError] = []

    if proxy.enabled:
        if not proxy.host:
            errors.append(ValidationError("proxy.host", "代理已启用但未设置代理地址"))
        elif len(proxy.host) > MAX_NAME_LENGTH:
            errors.append(ValidationError("proxy.host", f"代理地址过长（最大 {MAX_NAME_LENGTH} 字符）"))

        if proxy.port < MIN_PORT or proxy.port > MAX_PORT:
            errors.append(ValidationError("proxy.port", f"代理端口必须在 {MIN_PORT} - {MAX_PORT} 之间"))

    if proxy.test_url:
        if not HTTPS_URL_PATTERN.match(proxy.test_url):
            errors.append(ValidationError("proxy.test_url", "代理测试地址必须使用 https:// 协议"))
        else:
            parsed = urlparse(proxy.test_url)
            if not parsed.netloc or "." not in parsed.netloc:
                errors.append(ValidationError("proxy.test_url", "代理测试地址域名无效"))

    return errors


def _is_valid_repo_input(value: str) -> bool:
    """检查知识库输入格式是否合法。

    合法格式：
    - https://www.yuque.com/group/book（仅前两层路径，忽略后面的路径段）
    - group_login/book_slug

    不合法格式：
    - 裸字符串（无斜杠且非 URL）
    - https://www.yuque.com/group/book/doc-slug（超过两层路径）
    - group_login/book_slug/extra（斜杠数量超过 2 个）
    """
    if not value:
        return True

    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        path_parts = [p for p in parsed.path.split("/") if p]
        if len(path_parts) > 2:
            return False
        return True

    if "/" not in value:
        return False
    parts = value.split("/")
    if len(parts) != 2:
        return False
    group_login, book_slug = parts
    if not group_login.strip() or not book_slug.strip():
        return False
    if book_slug and not SLUG_PATTERN.match(book_slug) and not _is_cjk_string(book_slug):
        return False
    return True


def _has_invalid_path_chars(value: str) -> bool:
    """检查字符串中是否包含文件系统禁用字符。"""
    invalid_chars = '<>:"|?*'
    return any(c in value for c in invalid_chars)


def _is_cjk_string(value: str) -> bool:
    """检查字符串是否包含中日韩字符（用于支持中文 repo 名称）。"""
    return bool(re.search(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]", value))


def format_validation_errors(errors: list[ValidationError]) -> list[str]:
    """将校验错误格式化为用户友好的提示信息。"""
    if not errors:
        return []
    lines = ["配置验证失败："]
    for err in errors:
        lines.append(f"  - {err}")
    return lines
