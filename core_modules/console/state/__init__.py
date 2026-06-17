"""控制台状态辅助函数的公共导出。"""

from .manager import build_selected_docs_text, count_docs, remember_menu_index
from .view import (
    bool_text,
    build_confirmation_lines,
    build_connection_status,
    build_cookie_load_text,
    build_main_title,
    build_result_lines,
    build_status_lines,
    configured_cookie_value,
    cookie_edit_value,
    dedupe_error_text,
    format_rate_limit,
    mask_token,
)

__all__ = [
    "bool_text",
    "build_confirmation_lines",
    "build_connection_status",
    "build_cookie_load_text",
    "build_main_title",
    "build_result_lines",
    "build_selected_docs_text",
    "build_status_lines",
    "configured_cookie_value",
    "cookie_edit_value",
    "count_docs",
    "dedupe_error_text",
    "format_rate_limit",
    "mask_token",
    "remember_menu_index",
]
