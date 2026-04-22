"""控制台导出流程处理器。

本模块封装从导出前校验、确认、执行到结果展示的整条控制台导出链路。
"""

from __future__ import annotations

import threading

from core_modules.config.models import AppConfig, SessionState, active_auth_value, auth_mode_label, build_export_options, normalize_auth_mode
from core_modules.console.menu import run_confirmation, show_message
from core_modules.export.cli import execute_export, handle_export_error
from core_modules.export.errors import ExportCancelledError
from core_modules.export.progress import ExportProgressUI


def handle_export(
    config: AppConfig,
    session: SessionState,
    rate_limit_summary: str,
    *,
    build_client_from_config,
    apply_session_to_config,
    persist_config,
    append_console_log,
    build_selected_docs_text,
    build_confirmation_lines,
    build_result_lines,
    format_error_detail,
    format_rate_limit,
) -> str:
    """执行一次完整导出流程。

    参数:
        config: 当前应用配置。
        session: 当前控制台会话状态。
        rate_limit_summary: 上一次请求的限流摘要，用于失败时原样回传。
        build_client_from_config: 客户端构造函数。
        apply_session_to_config: 将会话写回配置的函数。
        persist_config: 保存配置的函数。
        append_console_log: 控制台日志追加函数。
        build_selected_docs_text: 文档范围文案构造函数。
        build_confirmation_lines: 确认页文案构造函数。
        build_result_lines: 结果页文案构造函数。
        format_error_detail: 异常详情格式化函数。
        format_rate_limit: 限流摘要格式化函数。

    返回:
        本次导出结束后的最新限流摘要。
    """
    credential = active_auth_value(config)
    label = auth_mode_label(normalize_auth_mode(config.auth_mode))
    if not session.connection_ok or not credential:
        session.token_status_message = f"请先设置有效 {label}"
        show_message(f"缺少 {label}", [f"请先在控制台中设置语雀 {label} 并刷新连接状态。"])
        return rate_limit_summary
    if not session.repo_input:
        session.status_message = "请先设置知识库"
        show_message("缺少知识库", ["请先手动输入知识库，或从列表选择知识库。"])
        return rate_limit_summary
    if session.current_user_login and "/" in session.repo_input:
        owner_login = session.repo_input.split("/", 1)[0]
        if owner_login != session.current_user_login:
            show_message("暂不支持导出", ["当前项目仅支持导出当前账号自己的个人知识库。", "非当前登录账号的知识库暂不支持导出，如受邀协作知识库。"])
            return rate_limit_summary
    config = apply_session_to_config(config, session)
    options = build_export_options(config, session.repo_input, session.selected_doc_ids)
    append_console_log(f"开始导出: 知识库={session.repo_input} 范围={build_selected_docs_text(session)}")
    if config.ui_preferences.confirm_before_export:
        confirmed = run_confirmation("确认导出", build_confirmation_lines(config, session))
        if not confirmed:
            session.status_message = "已取消导出"
            return rate_limit_summary
    client = build_client_from_config(config, credential)
    cancel_event = threading.Event()
    if hasattr(client, "set_cancel_event"):
        # 导出层支持外部中断时，把取消事件传给客户端，便于长请求尽快退出。
        client.set_cancel_event(cancel_event)
    progress_ui = ExportProgressUI()

    def _on_progress(snapshot) -> None:
        """桥接导出进度快照与 TUI 组件。"""
        if snapshot.current_stage == "已完成":
            progress_ui.finish(snapshot)
        else:
            progress_ui.update(snapshot)

    def _confirm_interrupt() -> bool:
        """收到 Ctrl+C 时，二次确认是否终止本次导出。"""
        append_console_log(f"确认中断导出: 知识库={session.repo_input}")
        confirmed = run_confirmation(
            "确认退出导出",
            [
                "检测到 Ctrl+C 中断请求。",
                '选择"退出"将立即退出本次导出。',
                '选择"取消"会返回导出界面，继续等待当前请求完成。',
            ],
            confirm_label="退出导出",
            cancel_label="继续导出",
        )
        if confirmed:
            cancel_event.set()
        return confirmed

    result_lines_holder: dict[str, list[str]] = {"lines": []}

    def _build_completion_lines(export_result):
        """在导出完成后缓存结果摘要，供主流程后续复用。"""
        lines = build_result_lines(config, session, export_result)
        result_lines_holder["lines"] = lines
        return lines

    try:
        result = progress_ui.run(
            lambda: execute_export(client, options, progress_callback=_on_progress),
            on_interrupt=_confirm_interrupt,
            on_complete=_build_completion_lines,
        )
    except KeyboardInterrupt:
        session.status_message = "已取消导出"
        session.last_error_text = "用户中断导出"
        append_console_log(f"导出已中止: 知识库={session.repo_input} 原因=用户中断")
        show_message("导出已取消", ["已按用户要求中止导出。", "已完成的文档和 checkpoint 会保留，可稍后继续导出。"])
        return format_rate_limit(client.last_rate_limit)
    except ExportCancelledError:
        session.status_message = "已取消导出"
        session.last_error_text = "用户中断导出"
        append_console_log(f"导出已中止: 知识库={session.repo_input} 原因=用户中断")
        show_message("导出已取消", ["已按用户要求中止导出。", "已完成的文档和 checkpoint 会保留，可稍后继续导出。"])
        return format_rate_limit(client.last_rate_limit)
    except Exception as exc:  # noqa: BLE001
        _, message = handle_export_error(exc)
        session.status_message = "导出失败"
        session.last_error_text = format_error_detail(exc)
        append_console_log(f"导出失败: 知识库={session.repo_input} 错误={session.last_error_text}")
        show_message("导出失败", [message])
        return format_rate_limit(client.last_rate_limit)
    if config.ui_preferences.auto_save_after_export:
        config = persist_config(config, session, "post_export")
    session.last_exported_docs = result.exported_docs
    # 优先复用进度界面生成的完成摘要，避免和最终弹窗文案出现细微差异。
    session.last_result_summary = result_lines_holder["lines"] or build_result_lines(config, session, result)
    session.status_message = "导出完成"
    session.last_error_text = ""
    append_console_log(f"导出成功: 知识库={session.repo_input} 成功={result.exported_docs} 跳过={result.skipped_docs} 失败={result.failed_docs}")
    return format_rate_limit(client.last_rate_limit)
