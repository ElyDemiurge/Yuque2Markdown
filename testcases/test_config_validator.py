"""Tests for config validation."""
import sys
sys.path.insert(0, ".")

from core_modules.config.models import AppConfig, ExportDefaultsConfig, ProxyConfig
from core_modules.config.validator import (
    validate_config,
    validate_export_defaults,
    validate_proxy,
    format_validation_errors,
    ValidationError,
    _is_valid_repo_input,
)


# ── Config-level validation ───────────────────────────────────

def test_valid_config_returns_no_errors():
    config = AppConfig()
    errors = validate_config(config)
    assert len(errors) == 0


def test_invalid_version():
    config = AppConfig(version=0)
    errors = validate_config(config)
    assert any(e.field == "version" for e in errors)


def test_short_token_warning():
    """Very short tokens should produce a warning (not an error, since empty is allowed)."""
    config = AppConfig(token="abc")
    errors = validate_config(config)
    assert any(e.field == "token" for e in errors)


# ── Export defaults validation ─────────────────────────────────

def test_empty_output_dir():
    defaults = ExportDefaultsConfig(output_dir="")
    errors = validate_export_defaults(defaults)
    assert any(e.field == "output_dir" for e in errors)


def test_output_dir_invalid_chars():
    defaults = ExportDefaultsConfig(output_dir="dir<name>")
    errors = validate_export_defaults(defaults)
    assert any(e.field == "output_dir" for e in errors)


def test_timeout_out_of_range():
    defaults = ExportDefaultsConfig(timeout=0)
    errors = validate_export_defaults(defaults)
    assert any(e.field == "timeout" for e in errors)


def test_timeout_too_large():
    defaults = ExportDefaultsConfig(timeout=999)
    errors = validate_export_defaults(defaults)
    assert any(e.field == "timeout" for e in errors)


def test_request_interval_out_of_range():
    defaults = ExportDefaultsConfig(request_interval=-1.0)
    errors = validate_export_defaults(defaults)
    assert any(e.field == "request_interval" for e in errors)


def test_retries_out_of_range():
    defaults = ExportDefaultsConfig(request_max_retries=-1)
    errors = validate_export_defaults(defaults)
    assert any(e.field == "request_max_retries" for e in errors)


def test_backoff_cross_field_validation():
    """max_backoff should be >= individual backoff values."""
    defaults = ExportDefaultsConfig(
        rate_limit_backoff_seconds=10.0,
        network_backoff_seconds=5.0,
        max_backoff_seconds=2.0,  # Too small
    )
    errors = validate_export_defaults(defaults)
    field_names = {e.field for e in errors}
    assert "max_backoff_seconds" in field_names


def test_max_docs_out_of_range():
    defaults = ExportDefaultsConfig(max_docs=0)
    errors = validate_export_defaults(defaults)
    assert any(e.field == "max_docs" for e in errors)


def test_assets_dir_with_separator():
    defaults = ExportDefaultsConfig(assets_dir_name="foo/bar")
    errors = validate_export_defaults(defaults)
    assert any(e.field == "assets_dir_name" for e in errors)


def test_assets_dir_whitespace():
    defaults = ExportDefaultsConfig(assets_dir_name="  foo  ")
    errors = validate_export_defaults(defaults)
    assert any(e.field == "assets_dir_name" for e in errors)


def test_attachment_suffix_invalid():
    defaults = ExportDefaultsConfig(attachment_suffixes=["pdf"])
    errors = validate_export_defaults(defaults)
    assert any(e.field == "attachment_suffixes" for e in errors)


# ── Proxy validation ───────────────────────────────────────────

def test_proxy_enabled_without_host():
    proxy = ProxyConfig(enabled=True, host="", port=7890)
    errors = validate_proxy(proxy)
    assert any(e.field == "proxy.host" for e in errors)


def test_proxy_port_out_of_range():
    proxy = ProxyConfig(enabled=True, host="127.0.0.1", port=99999)
    errors = validate_proxy(proxy)
    assert any(e.field == "proxy.port" for e in errors)


def test_proxy_test_url_invalid():
    proxy = ProxyConfig(enabled=False, test_url="not-a-url")
    errors = validate_proxy(proxy)
    assert any(e.field == "proxy.test_url" for e in errors)


def test_proxy_disabled_valid():
    proxy = ProxyConfig(enabled=False, host="", port=7890, test_url="https://example.com")
    errors = validate_proxy(proxy)
    assert len(errors) == 0


def test_proxy_enabled_valid():
    proxy = ProxyConfig(enabled=True, host="127.0.0.1", port=7890, test_url="https://example.com")
    errors = validate_proxy(proxy)
    assert len(errors) == 0


# ── Error formatting ─────────────────────────────────────────

def test_format_validation_errors():
    errors = [
        ValidationError("field1", "must not be empty"),
        ValidationError("field2", "out of range"),
    ]
    lines = format_validation_errors(errors)
    assert "配置验证失败" in lines[0]
    assert any("field1" in line for line in lines)
    assert any("field2" in line for line in lines)


def test_format_empty_errors():
    assert format_validation_errors([]) == []


# ── Repo input validation ─────────────────────────────────────

def test_repo_input_bare_string_rejected():
    """裸字符串（无斜杠）应被拒绝。"""
    assert _is_valid_repo_input("myrepo") is False


def test_repo_input_group_book_accepted():
    assert _is_valid_repo_input("group_login/book_slug") is True


def test_repo_input_chinese_accepted():
    """中文知识库名称应被接受。"""
    assert _is_valid_repo_input("我的组/我的书") is True


def test_repo_input_url_three_layers_rejected():
    """URL 路径超过两层（group/book/doc）应被拒绝。"""
    assert _is_valid_repo_input("https://www.yuque.com/group/book/doc-slug") is False
    assert _is_valid_repo_input("https://www.yuque.com/a/b/c/d") is False


def test_repo_input_url_two_layers_accepted():
    """URL 恰好两层路径应被接受。"""
    assert _is_valid_repo_input("https://www.yuque.com/group/book") is True
    assert _is_valid_repo_input("https://yuque.com/group/book") is True


def test_repo_input_url_with_query_accepted():
    """带 query string 的 URL 应被接受（前两层）。"""
    assert _is_valid_repo_input("https://www.yuque.com/group/book?ref=share") is True


def test_repo_input_too_many_slashes():
    """非 URL 格式但有多个斜杠应被拒绝。"""
    assert _is_valid_repo_input("a/b/c") is False


# ── Output dir path traversal ────────────────────────────────

def test_output_dir_path_traversal_rejected():
    """output_dir 包含 .. 应被拒绝。"""
    defaults = ExportDefaultsConfig(output_dir="../outside")
    errors = validate_export_defaults(defaults)
    assert any(e.field == "output_dir" for e in errors)


# ── Proxy test_url protocol validation ──────────────────────

def test_proxy_test_url_http_rejected():
    """http:// 代理测试地址应被拒绝。"""
    proxy = ProxyConfig(enabled=False, test_url="http://example.com")
    errors = validate_proxy(proxy)
    assert any(e.field == "proxy.test_url" for e in errors)


def test_proxy_test_url_https_accepted():
    """https:// 代理测试地址应被接受。"""
    proxy = ProxyConfig(enabled=False, test_url="https://example.com")
    errors = validate_proxy(proxy)
    assert len(errors) == 0


def test_proxy_test_url_no_domain_rejected():
    """代理测试地址域名无效应被拒绝。"""
    proxy = ProxyConfig(enabled=False, test_url="https://")
    errors = validate_proxy(proxy)
    assert any(e.field == "proxy.test_url" for e in errors)
