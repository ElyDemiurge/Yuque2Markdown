"""控制台状态展示辅助函数。

本模块负责把配置和会话状态转成界面展示文本，不做任何网络或文件操作。
"""

from __future__ import annotations

from core_modules.config.models import AUTH_MODE_COOKIE, AppConfig, SessionState, auth_mode_label, normalize_auth_mode, summarize_attachment_suffixes
from core_modules.config.store import config_path


def bool_text(value: bool) -> str:
    """将布尔值转成中文开关状态。"""
    return "开启" if value else "关闭"


def mask_token(token: str) -> str:
    """按控制台展示需求遮罩 Token。"""
    if not token:
        return "未设置"
    return "******" + token[-4:] if len(token) > 4 else "******"


def _confirm_value_line(label: str, value: str) -> str:
    """构造确认页使用的带缩进键值行。"""
    return f"    {label}: {value}"


def _result_value_line(label: str, value: str) -> str:
    """构造结果页使用的带缩进键值行。"""
    return f"  {label}: {value}"


def dedupe_error_text(status_message: str, error_text: str) -> str:
    """去除已包含在状态文案中的重复错误详情。"""
    detail = (error_text or "").strip()
    if not detail:
        return ""
    if detail in status_message:
        return ""
    return detail


def format_rate_limit(rate_limit: dict[str, str | int | None]) -> str:
    """格式化接口限流信息，便于在状态栏与日志中复用。"""
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
    """构造带颜色前缀的连接状态文本。

    参数:
        status_message: 连接检查后的主状态文本。
        rate_limit_summary: 限流摘要。
        error_text: 额外错误详情。

    返回:
        供菜单状态栏直接展示的字符串。
    """
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
    """生成导出确认页的多行文本。

    参数:
        config: 当前应用配置。
        session: 当前会话状态。
        build_selected_docs_text: 文档范围文案生成函数，使用注入方式便于测试。

    返回:
        可直接传给确认弹窗的字符串列表。
    """
    defaults = config.export_defaults
    auth_mode = normalize_auth_mode(config.auth_mode)
    if auth_mode == AUTH_MODE_COOKIE:
        attachment_status = f"Cookie 登录，可下载 {summarize_attachment_suffixes(defaults.attachment_suffixes)}"
    else:
        attachment_status = "使用 Token 登录时无法下载附件以及选择下载附件类型，语雀附件会保留原始链接"
    lines = [
        "[连接与身份]",
        _confirm_value_line("当前用户", session.current_user_label),
        _confirm_value_line("登录方式", auth_mode_label(auth_mode)),
        _confirm_value_line("Token", f"{'已设置' if config.token else '未设置'} | 保存到配置文件 {bool_text(config.persist_token)}"),
        _confirm_value_line("Cookie", f"{'已设置' if config.cookie else '未设置'} | 保存到配置文件 {bool_text(config.persist_cookie)}"),
        "",
        "[知识库与范围]",
        _confirm_value_line("知识库", session.repo_display_name or session.repo_input or "未设置"),
        _confirm_value_line("命名空间", session.repo_namespace or session.repo_input or "未设置"),
    ]
    if session.repo_url:
        lines.append(_confirm_value_line("链接", session.repo_url))
    lines.extend(
        [
            _confirm_value_line("文档范围", build_selected_docs_text(session)),
            "",
            "[导出路径与资源]",
            _confirm_value_line("输出目录", defaults.output_dir),
            _confirm_value_line(
                "导出选项",
                f"已完成文档可继续跳过 {bool_text(defaults.resume)} | 出错后立即停止 {bool_text(defaults.strict)} | 下载图片到本地 {bool_text(defaults.offline_assets)}",
            ),
            _confirm_value_line("资源目录", defaults.assets_dir_name),
            _confirm_value_line("附件下载", attachment_status),
            _confirm_value_line(
                "请求设置",
                f"间隔 {defaults.request_interval}s | 请求超时 {defaults.timeout}s | 检查 Token 超时 {defaults.token_check_timeout}s",
            ),
            _confirm_value_line(
                "重试设置",
                f"最多重试 {defaults.request_max_retries} 次 | 限流后首次等待 {defaults.rate_limit_backoff_seconds}s | 网络错误后首次等待 {defaults.network_backoff_seconds}s",
            ),
            _confirm_value_line("等待上限", f"单次重试最多等待 {defaults.max_backoff_seconds}s"),
            _confirm_value_line("导出上限", "不限" if defaults.max_docs is None else f"{defaults.max_docs} 篇"),
            "",
            "[保存状态]",
            _confirm_value_line("配置文件", config_path().name),
            _confirm_value_line("完整路径", str(config_path())),
            _confirm_value_line("未保存修改", bool_text(session.dirty)),
        ]
    )
    return lines


def build_result_lines(config: AppConfig, session: SessionState, result, *, build_selected_docs_text) -> list[str]:
    """生成导出完成后的摘要文本。"""
    lines = [
        "[导出结果]",
        _result_value_line("知识库", session.repo_display_name or result.repo.name or result.repo.book_slug),
        _result_value_line("输出目录", config.export_defaults.output_dir),
        _result_value_line("文档范围", build_selected_docs_text(session)),
        f"  成功: {result.exported_docs} | 跳过: {result.skipped_docs} | 失败: {result.failed_docs}",
    ]
    if result.elapsed_seconds is not None:
        lines.append(_result_value_line("总耗时", f"{result.elapsed_seconds:.1f} 秒"))
    lines.append(_result_value_line("改写内部链接", str(result.rewritten_links)))
    if result.total_warnings > 0:
        lines.append(_result_value_line("总警告数", str(result.total_warnings)))
    if result.total_downloaded > 0:
        lines.append(
            _result_value_line(
                "资源下载",
                f"成功 {result.total_downloaded}"
                + (f" | 失败 {result.total_download_failed}" if result.total_download_failed > 0 else ""),
            )
        )
    elif result.total_download_failed > 0:
        lines.append(_result_value_line("资源下载", f"失败 {result.total_download_failed}"))
    if result.failed_items:
        lines.append("  [失败项预览]")
        lines.extend(f"  - {item}" for item in result.failed_items[:5])
    return lines


def build_status_lines(config: AppConfig, session: SessionState, rate_limit_summary: str) -> list[str]:
    """构造主菜单底部状态栏文本。

    参数:
        config: 当前应用配置。
        session: 当前会话状态。
        rate_limit_summary: 最近一次请求的限流摘要。

    返回:
        固定顺序的状态行列表。
    """
    token_msg = session.token_status_message
    auth_mode = normalize_auth_mode(config.auth_mode)
    auth_label = auth_mode_label(auth_mode)
    has_credential = bool(config.cookie if auth_mode == AUTH_MODE_COOKIE else config.token)
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
    elif has_credential:
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
            token_status = f"已设置 {auth_label}（未刷新连接）"
    else:
        token_color = ""
        token_status = f"未设置 {auth_label}"

    # 知识库状态优先显示带名称的命名空间，其次回退到原始输入。
    if session.repo_namespace:
        repo_status = f"{session.repo_display_name or session.repo_namespace}"
    elif session.repo_input:
        repo_status = session.repo_input
    else:
        repo_status = "未选择"

    # 如果用户没有显式勾选文档，则展示当前知识库的总文档数。
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
        f"{token_color}{auth_label}: {token_status}",
        f"知识库: {repo_status}",
        f"导出范围: {scope_status}",
        f"{network_color}网络: {network_status}",
        f"配置文件: {config_path().name}",
    ]
