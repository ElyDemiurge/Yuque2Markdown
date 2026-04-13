"""View/state presentation helpers for Yuque2Markdown console."""

from __future__ import annotations

from core_modules.config.models import AppConfig, SessionState
from core_modules.config.store import config_path


def bool_text(value: bool) -> str:
    return "开启" if value else "关闭"


def mask_token(token: str) -> str:
    if not token:
        return "未设置"
    return "******" + token[-4:] if len(token) > 4 else "******"


def dedupe_error_text(status_message: str, error_text: str) -> str:
    detail = (error_text or "").strip()
    if not detail:
        return ""
    if detail in status_message:
        return ""
    return detail


def format_rate_limit(rate_limit: dict[str, str | int | None]) -> str:
    limit = rate_limit.get("limit")
    remaining = rate_limit.get("remaining")
    reset = rate_limit.get("reset")
    parts = [
        f"X-RateLimit-Limit={limit if limit is not None else '-'}",
        f"X-RateLimit-Remaining={remaining if remaining is not None else '-'}",
    ]
    if reset:
        parts.append(f"X-RateLimit-Reset={reset}")
    return " | ".join(parts)


def build_connection_status(status_message: str, rate_limit_summary: str, error_text: str = "") -> str:
    base = f"连接状态: {status_message}"
    detail = dedupe_error_text(status_message, error_text)
    if detail:
        base = f"{base} | error={detail}"
    if "处理中" in status_message or "正在" in status_message:
        return f"[BLUE] {base}"
    if "限流" in status_message or rate_limit_summary == "429 LIMIT":
        return f"[YELLOW] {base}"
    if "失败" in status_message or "无效" in status_message:
        return f"[RED] {base}"
    if "已刷新" in status_message or "正常" in status_message:
        if not rate_limit_summary or rate_limit_summary == "暂无":
            return f"[GREEN] {base}"
        return f"[GREEN] {base} | {rate_limit_summary}"
    if not rate_limit_summary or rate_limit_summary == "暂无":
        return base
    return f"{base} | {rate_limit_summary}"


def build_confirmation_lines(config: AppConfig, session: SessionState, *, build_selected_docs_text) -> list[str]:
    lines = [
        "[连接与身份]",
        f"当前用户: {session.current_user_label}",
        f"Token 状态: {'已设置' if config.token else '未设置'} | 持久化: {bool_text(config.persist_token)}",
        "[知识库与范围]",
        f"知识库: {session.repo_display_name or session.repo_input or '未设置'}",
        f"命名空间: {session.repo_namespace or session.repo_input or '未设置'}",
    ]
    if session.repo_url:
        lines.append(f"链接: {session.repo_url}")
    lines.extend(
        [
            f"文档范围: {build_selected_docs_text(session)}",
            "[导出路径与资源]",
            f"输出目录: {config.export_defaults.output_dir}",
            f"断点续导: {bool_text(config.export_defaults.resume)}",
            f"严格模式: {bool_text(config.export_defaults.strict)}",
            f"离线资源: {bool_text(config.export_defaults.offline_assets)}",
            f"资源目录: {config.export_defaults.assets_dir_name}",
            f"API 请求间隔: {config.export_defaults.request_interval}",
            f"API 请求超时: {config.export_defaults.timeout}s",
            f"检查 Token 可用性超时: {config.export_defaults.token_check_timeout}s",
            f"API 请求失败重试次数: {config.export_defaults.request_max_retries}",
            f"限流初始等待: {config.export_defaults.rate_limit_backoff_seconds}s",
            f"网络错误初始等待: {config.export_defaults.network_backoff_seconds}s",
            f"最大重试等待时长: {config.export_defaults.max_backoff_seconds}s",
            f"最多导出文档数: {'不限' if config.export_defaults.max_docs is None else config.export_defaults.max_docs}",
            "[保存状态]",
            f"配置文件: {config_path()}",
            f"未保存修改: {bool_text(session.dirty)}",
        ]
    )
    return lines


def build_result_lines(config: AppConfig, session: SessionState, result, *, build_selected_docs_text) -> list[str]:
    lines = [
        "[导出结果]",
        f"知识库: {session.repo_display_name or result.repo.name or result.repo.book_slug}",
        f"输出目录: {config.export_defaults.output_dir}",
        f"文档范围: {build_selected_docs_text(session)}",
        f"成功: {result.exported_docs} | 跳过: {result.skipped_docs} | 失败: {result.failed_docs}",
    ]
    if result.elapsed_seconds is not None:
        lines.append(f"耗时: {result.elapsed_seconds:.1f} 秒")
    lines.append(f"重写内部链接: {result.rewritten_links}")
    if result.total_warnings > 0:
        lines.append(f"总警告数: {result.total_warnings}")
    if result.total_downloaded > 0:
        lines.append(
            f"资源下载: 成功 {result.total_downloaded}"
            + (f" | 失败 {result.total_download_failed}" if result.total_download_failed > 0 else "")
        )
    elif result.total_download_failed > 0:
        lines.append(f"资源下载: 失败 {result.total_download_failed}")
    if result.failed_items:
        lines.append("[失败项预览]")
        lines.extend(f"- {item}" for item in result.failed_items[:5])
    lines.append("配置保存: 已自动保存" if config.ui_preferences.auto_save_after_export else "配置保存: 未自动保存")
    return lines


def build_status_lines(config: AppConfig, session: SessionState, rate_limit_summary: str) -> list[str]:
    token_msg = session.token_status_message
    if session.connection_ok:
        if "已修改" in token_msg or "请测试" in token_msg or "请刷新" in token_msg:
            token_color = "[YELLOW] "
            token_status = token_msg
        elif "限流" in token_msg or "429" in token_msg:
            token_color = "[YELLOW] "
            token_status = token_msg
            if session.last_error_text and session.last_error_text not in token_status:
                token_status = f"{token_status}（Error = {session.last_error_text}）"
        elif "失败" in token_msg or "无效" in token_msg or "异常" in token_msg:
            token_color = "[RED] "
            token_status = token_msg
            if session.last_error_text and session.last_error_text not in token_status:
                token_status = f"{token_status}（Error = {session.last_error_text}）"
        else:
            token_color = "[GREEN] "
            token_status = f"已连接（{session.current_user_label}）"
    elif config.token:
        if "限流" in token_msg or "429" in token_msg:
            token_color = "[YELLOW] "
            token_status = token_msg
            if session.last_error_text and session.last_error_text not in token_status:
                token_status = f"{token_status}（Error = {session.last_error_text}）"
        elif "失败" in token_msg or "无效" in token_msg or "异常" in token_msg:
            token_color = "[RED] "
            token_status = token_msg
            if session.last_error_text and session.last_error_text not in token_status:
                token_status = f"{token_status}（Error = {session.last_error_text}）"
        elif token_msg:
            token_color = "[YELLOW] " if any(k in token_msg for k in ("请刷新", "请测试", "已修改", "重新设置")) else "[RED] "
            token_status = token_msg
        else:
            token_color = ""
            token_status = "已设置 Token（未刷新连接）"
    else:
        token_color = ""
        token_status = "未设置 Token"

    if session.repo_namespace:
        repo_status = f"{session.repo_display_name or session.repo_namespace}"
    elif session.repo_input:
        repo_status = session.repo_input
    else:
        repo_status = "未选择"

    if session.selected_doc_ids:
        scope_status = f"已选 {len(session.selected_doc_ids)} 篇"
    elif session.selected_doc_count:
        scope_status = f"全部（共 {session.selected_doc_count} 篇）"
    else:
        scope_status = "全部"

    proxy = config.export_defaults.proxy
    if proxy.enabled and proxy.host:
        proxy_base = f"代理开启（{proxy.host}:{proxy.port}）"
    elif proxy.host:
        proxy_base = "代理关闭"
    else:
        proxy_base = "代理未设置"

    network_color = ""
    test_msg = session.network_test_message
    if test_msg:
        if "代理测试成功" in test_msg:
            network_color = "[GREEN] "
            network_status = f"{proxy_base} | 代理连接成功"
        elif "代理测试失败" in test_msg:
            network_color = "[RED] "
            test_detail = test_msg.replace("代理测试失败：", "")
            network_status = f"{proxy_base} | 代理连接失败（{test_detail}）" if test_detail else f"{proxy_base} | 代理连接失败"
        elif "网络正常" in test_msg:
            network_color = "[GREEN] "
            network_status = f"{proxy_base} | {test_msg}"
        elif "网络异常" in test_msg:
            network_color = "[RED] "
            network_status = f"{proxy_base} | {test_msg}"
        else:
            network_status = f"{proxy_base} | {test_msg}"
    else:
        network_status = proxy_base

    return [
        f"{token_color}Token: {token_status}",
        f"知识库: {repo_status}",
        f"导出文章范围: {scope_status}",
        f"{network_color}网络: {network_status}",
        f"配置文件: {config_path().name}",
    ]
