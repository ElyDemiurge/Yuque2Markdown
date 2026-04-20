"""控制台错误处理辅助函数。"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core_modules.config.models import SessionState


@dataclass(slots=True)
class ErrorContext:
    """描述一次错误处理所需的上下文。"""

    title: str
    error: Exception
    log_prefix: str = ""


@dataclass(slots=True)
class ErrorResult:
    """封装错误处理结果。"""

    message: str
    detail: str
    should_raise: bool = False


def format_error_detail(exc: Exception) -> str:
    """将异常格式化为“状态码 / 消息”的形式。"""
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
    """错误发生后，统一更新会话状态。"""
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
    """处理连接异常，并根据代理状态给出更具体的提示。"""
    from core_modules.export.errors import YuqueRateLimitError

    error_str = str(exc)

    # 限流错误
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

    # 代理相关错误
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

        message = "连接检查失败（代理正常，请检查登录凭据或网络）"
        update_session_error_state(
            session,
            token_message=message,
            error_text=error_str,
            connection_ok=False,
        )
        if log_func:
            log_func(f"刷新连接失败（API 问题）: {error_str}")
        return ErrorResult(message=message, detail=error_str)

    # 其他通用连接错误
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
    """处理单篇文档导出过程中的异常。"""
    from core_modules.export.errors import ExportError, YuquePermissionError, YuqueRateLimitError

    is_rate_limit = isinstance(exc, YuqueRateLimitError)
    is_known_error = isinstance(exc, (YuquePermissionError, YuqueRateLimitError, ExportError))

    if doc_id and doc_id not in checkpoint.failed_doc_ids:
        checkpoint.failed_doc_ids.append(doc_id)

    # 更新断点状态
    from core_modules.export.models import DocExportState

    if doc_id and doc_id not in checkpoint.doc_states:
        checkpoint.doc_states[doc_id] = DocExportState(doc_id=doc_id)
    if doc_id:
        checkpoint.doc_states[doc_id].stage = "failed"
    save_checkpoint(repo_dir, checkpoint)

    # 更新导出结果汇总
    result.failed_docs += 1
    result.failed_items.append(f"{doc_title}: {exc}")

    # 更新进度快照
    error_msg = f"{doc_title}: {exc}"
    recent_failed = _push_recent(progress.recent_failed, error_msg)
    waiting_preview = _advance_waiting_preview(progress.waiting_preview, doc_title)

    # 调用方后续会基于这些字段触发进度刷新。
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
    """向最近列表追加一项，并限制最大长度。"""
    result = list(recent)
    result.append(item)
    if len(result) > max_size:
        result = result[-max_size:]
    return result


def _advance_waiting_preview(preview: list, current: str) -> list:
    """更新等待队列预览，移除当前正在处理的项目。"""
    result = [p for p in preview if p != current]
    return result
