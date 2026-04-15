"""控制台导出流程处理器。"""

from core_modules.config.models import AppConfig, SessionState, build_export_options
from core_modules.console.menu import run_confirmation, show_message
from core_modules.export.cli import execute_export, handle_export_error
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
    """执行一次完整导出流程。"""
    token = (config.token or "").strip()
    if not session.connection_ok or not token:
        session.token_status_message = "请先设置有效 Token"
        show_message("缺少 Token", ["请先在控制台中设置 Yuque Token 并刷新连接状态。"])
        return rate_limit_summary
    if not session.repo_input:
        session.status_message = "请先设置知识库"
        show_message("缺少知识库", ["请先手动输入知识库，或从列表选择知识库。"])
        return rate_limit_summary
    config = apply_session_to_config(config, session)
    options = build_export_options(config, session.repo_input, session.selected_doc_ids)
    append_console_log(f"EXPORT_START repo={session.repo_input} scope={build_selected_docs_text(session)}")
    if config.ui_preferences.confirm_before_export:
        confirmed = run_confirmation("确认导出", build_confirmation_lines(config, session))
        if not confirmed:
            session.status_message = "已取消导出"
            return rate_limit_summary
    client = build_client_from_config(config, token)
    progress_ui = ExportProgressUI()

    def _on_progress(snapshot) -> None:
        if snapshot.current_stage == "已完成":
            progress_ui.finish(snapshot)
        else:
            progress_ui.update(snapshot)

    def _confirm_interrupt() -> bool:
        append_console_log(f"EXPORT_INTERRUPT_CONFIRM repo={session.repo_input}")
        return run_confirmation(
            "确认退出导出",
            [
                "检测到 Ctrl+C 中断请求。",
                '选择"退出"将立即退出本次导出。',
                '选择"取消"会返回导出界面，继续等待当前请求完成。',
            ],
            confirm_label="退出导出",
            cancel_label="继续导出",
        )

    result_lines_holder: dict[str, list[str]] = {"lines": []}

    def _build_completion_lines(export_result):
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
        append_console_log(f"EXPORT_ABORT repo={session.repo_input} reason=KeyboardInterrupt")
        show_message("导出已取消", ["已按用户要求中止导出。", "已完成的文档和 checkpoint 会保留，可稍后继续导出。"])
        return format_rate_limit(client.last_rate_limit)
    except Exception as exc:  # noqa: BLE001
        _, message = handle_export_error(exc)
        session.status_message = "导出失败"
        session.last_error_text = format_error_detail(exc)
        append_console_log(f"EXPORT_FAIL repo={session.repo_input} error={session.last_error_text}")
        show_message("导出失败", [message])
        return format_rate_limit(client.last_rate_limit)
    if config.ui_preferences.auto_save_after_export:
        config = persist_config(config, session, "post_export")
    session.last_exported_docs = result.exported_docs
    session.last_result_summary = result_lines_holder["lines"] or build_result_lines(config, session, result)
    session.status_message = "导出完成"
    session.last_error_text = ""
    append_console_log(
        f"EXPORT_SUCCESS repo={session.repo_input} exported={result.exported_docs} skipped={result.skipped_docs} failed={result.failed_docs}"
    )
    return format_rate_limit(client.last_rate_limit)
