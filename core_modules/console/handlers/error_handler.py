"""Common error handling utilities for Yuque2Markdown console.

This module provides centralized error handling patterns to reduce code duplication.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core_modules.config.models import SessionState


@dataclass(slots=True)
class ErrorContext:
    """Context information for error handling."""

    title: str
    error: Exception
    log_prefix: str = ""


@dataclass(slots=True)
class ErrorResult:
    """Result of error handling."""

    message: str
    detail: str
    should_raise: bool = False


def format_error_detail(exc: Exception) -> str:
    """Format error detail as 'status / message' format."""
    status = getattr(exc, "status", None)
    message = str(exc)
    if status:
        return f"{status} / {message}"
    return message


def update_session_error_state(
    session: "SessionState",
    *,
    token_message: str = "",
    error_text: str = "",
    connection_ok: bool = False,
    current_user_label: str = "未检查",
) -> None:
    """Update session state after an error occurs.

    This consolidates the common pattern of updating multiple session fields
    when an error occurs during connection, export, or other operations.
    """
    if token_message:
        session.token_status_message = token_message
    if error_text:
        session.last_error_text = error_text
    session.connection_ok = connection_ok
    session.current_user_label = current_user_label


def handle_connection_error(
    session: "SessionState",
    exc: Exception,
    *,
    proxy_enabled: bool = False,
    proxy_host: str = "",
    proxy_test_func=None,
    log_func=None,
) -> ErrorResult:
    """Handle connection errors with proxy-aware error messages.

    Args:
        session: Session state to update
        exc: The exception that occurred
        proxy_enabled: Whether proxy is enabled
        proxy_host: Proxy host address
        proxy_test_func: Function to test proxy connectivity
        log_func: Function to log messages

    Returns:
        ErrorResult with error details
    """
    from core_modules.export.errors import YuqueRateLimitError

    error_str = str(exc)

    # Rate limit error
    if isinstance(exc, YuqueRateLimitError):
        retry_after = getattr(exc, "retry_after", None)
        wait_hint = f"建议等待 {int(retry_after)} 秒后再试" if retry_after else "建议稍后再试"
        message = f"触发语雀限流，{wait_hint}"
        detail = format_error_detail(exc)
        update_session_error_state(
            session,
            token_message=message,
            error_text=detail,
            connection_ok=False,
        )
        if log_func:
            log_func(f"刷新连接限流: {detail}")
        return ErrorResult(message=message, detail=detail)

    # Proxy-related error
    if proxy_enabled and proxy_host and proxy_test_func:
        proxy_ok, proxy_msg = proxy_test_func()
        if not proxy_ok:
            message = f"代理连接失败：{proxy_msg}"
            update_session_error_state(
                session,
                token_message=message,
                error_text=proxy_msg,
                connection_ok=False,
            )
            if log_func:
                log_func(f"刷新连接失败（代理问题）: {proxy_msg}")
            return ErrorResult(message=message, detail=proxy_msg)

        message = "连接检查失败（代理正常，请检查 Token 或网络）"
        update_session_error_state(
            session,
            token_message=message,
            error_text=error_str,
            connection_ok=False,
        )
        if log_func:
            log_func(f"刷新连接失败（API 问题）: {error_str}")
        return ErrorResult(message=message, detail=error_str)

    # Generic connection error
    message = "连接检查失败"
    update_session_error_state(
        session,
        token_message=message,
        error_text=error_str,
        connection_ok=False,
    )
    if log_func:
        log_func(f"刷新连接失败: {error_str}")
    return ErrorResult(message=message, detail=error_str)


def handle_export_doc_error(
    *,
    exc: Exception,
    doc_id: int | None,
    doc_title: str,
    checkpoint,
    repo_dir,
    result,
    progress,
    log,
    strict_mode: bool = False,
) -> bool:
    """Handle errors during document export.

    This consolidates the error handling pattern in exporter.py.

    Args:
        exc: The exception that occurred
        doc_id: Document ID (may be None)
        doc_title: Document title for logging
        checkpoint: Checkpoint state to update
        repo_dir: Repository directory for saving checkpoint
        result: Export result to update
        progress: Progress snapshot to update
        log: Export logger
        strict_mode: Whether to re-raise the exception

    Returns:
        True if the exception should be re-raised, False otherwise
    """
    from core_modules.export.errors import ExportError, YuquePermissionError, YuqueRateLimitError

    is_rate_limit = isinstance(exc, YuqueRateLimitError)
    is_known_error = isinstance(exc, (YuquePermissionError, YuqueRateLimitError, ExportError))

    if doc_id and doc_id not in checkpoint.failed_doc_ids:
        checkpoint.failed_doc_ids.append(doc_id)

    # Update checkpoint state
    from core_modules.export.models import DocExportState

    if doc_id and doc_id not in checkpoint.doc_states:
        checkpoint.doc_states[doc_id] = DocExportState(doc_id=doc_id)
    if doc_id:
        checkpoint.doc_states[doc_id].stage = "failed"
    save_checkpoint(repo_dir, checkpoint)

    # Update result
    result.failed_docs += 1
    result.failed_items.append(f"{doc_title}: {exc}")

    # Update progress
    error_msg = f"{doc_title}: {exc}"
    recent_failed = _push_recent(progress.recent_failed, error_msg)
    waiting_preview = _advance_waiting_preview(progress.waiting_preview, doc_title)

    # Note: The caller should call _emit_progress with the updated values
    # This function just returns the updated lists
    progress.recent_failed = recent_failed
    progress.waiting_preview = waiting_preview
    progress.processed_docs += 1
    progress.failed_docs = result.failed_docs
    progress.waiting_docs = max(0, progress.waiting_docs - 1)
    progress.current_doc_title = doc_title
    progress.current_stage = "导出失败"
    progress.active_tasks = [f"失败: {doc_title}"]
    progress.latest_event = f"{doc_title} 导出失败"
    progress.latest_error = error_msg

    log.doc_failed(doc_title, str(exc))

    return strict_mode or is_rate_limit


def _push_recent(recent: list, item: str, max_size: int = 10) -> list:
    """Add item to recent list, maintaining max size."""
    result = list(recent)
    result.append(item)
    if len(result) > max_size:
        result = result[-max_size:]
    return result


def _advance_waiting_preview(preview: list, current: str) -> list:
    """Advance waiting preview, removing current item if present."""
    result = [p for p in preview if p != current]
    return result
