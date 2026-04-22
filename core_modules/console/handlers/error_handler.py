"""控制台错误处理辅助函数。

本模块集中放置错误格式化、会话状态回填和导出异常汇总逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core_modules.config.models import SessionState


@dataclass(slots=True)
class ErrorResult:
    """封装错误处理结果。

    属性:
        message: 面向用户展示的主提示。
        detail: 更完整的错误详情，通常用于状态栏或日志。
        should_raise: 是否需要由调用方继续抛出异常。
    """

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
    """错误发生后统一更新会话状态。

    参数:
        session: 当前控制台会话状态。
        token_message: 需要展示在登录状态区域的文案。
        error_text: 错误详情。
        connection_ok: 连接状态标记。
        current_user_label: 当前用户展示文案，出错时通常回退为“未检查”。
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
    """处理连接异常，并根据代理状态给出更具体的提示。

    返回:
        ``ErrorResult``，便于调用方继续拼装状态栏或日志。
    """
    from core_modules.export.errors import YuqueRateLimitError

    error_str = str(exc)

    # 语雀限流需要给出等待建议，提示优先级高于通用连接错误。
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

    # 代理开启时，优先区分“代理本身异常”和“代理可用但上游接口失败”。
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

    # 未开启代理，或无法进一步细分原因时，统一降级为通用连接错误。
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
    """处理单篇文档导出过程中的异常。

    参数:
        exc: 当前异常对象。
        doc_id: 文档 ID，可能为空。
        doc_title: 文档标题。
        checkpoint: 当前导出断点对象。
        repo_dir: 当前知识库的输出目录。
        result: 导出结果汇总对象。
        progress: 进度快照对象。
        log: 导出日志记录器。
        strict_mode: 严格模式；开启后，任意单文档失败都要求上层终止流程。

    返回:
        ``True`` 表示调用方应立即终止后续导出；``False`` 表示可继续处理后续文档。
    """
    from core_modules.export.errors import ExportError, YuquePermissionError, YuqueRateLimitError
    from core_modules.export.models import DocExportState
    from core_modules.export.checkpoint import save_checkpoint

    if doc_id is not None and doc_id not in checkpoint.failed_doc_ids:
        checkpoint.failed_doc_ids.append(doc_id)

    # 为失败文档补齐断点状态，便于下次续传时快速跳过或重试。
    if doc_id is not None and doc_id not in checkpoint.doc_states:
        checkpoint.doc_states[doc_id] = DocExportState(doc_id=doc_id)
    if doc_id is not None:
        checkpoint.doc_states[doc_id].stage = "failed"
    save_checkpoint(repo_dir, checkpoint)

    # 同步更新最终结果汇总和最近失败预览，供 UI 与日志直接复用。
    result.failed_docs += 1
    result.failed_items.append(f"{doc_title}: {exc}")

    error_msg = f"{doc_title}: {exc}"
    recent_failed = _push_recent(progress.recent_failed, error_msg)
    waiting_preview = _advance_waiting_preview(progress.waiting_preview, doc_title)

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

    return strict_mode or isinstance(exc, YuqueRateLimitError)


def _push_recent(recent: list, item: str, max_size: int = 10) -> list:
    """向最近记录列表追加一项，并限制最大长度。"""
    result = list(recent)
    result.append(item)
    if len(result) > max_size:
        result = result[-max_size:]
    return result


def _advance_waiting_preview(preview: list, current: str) -> list:
    """更新等待队列预览，移除当前正在处理的项目。"""
    result = [p for p in preview if p != current]
    return result
