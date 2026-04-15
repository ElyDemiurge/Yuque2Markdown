"""控制台连接状态处理逻辑。"""

from __future__ import annotations

import threading

from core_modules.config.models import AppConfig, SessionState
from core_modules.console.menu import MenuRefreshState
from core_modules.export.cli import list_accessible_repos
from core_modules.export.errors import YuqueRateLimitError


def refresh_connection_state(
    token: str,
    config: AppConfig,
    session: SessionState,
    *,
    build_client_from_config,
    build_connection_status,
    format_rate_limit,
    format_error_detail,
    append_console_log,
    interactive: bool = False,
) -> tuple[list[dict], str, str, bool]:
    """刷新 Token、当前用户和连接状态。"""
    session.network_test_message = ""
    if not token:
        session.current_user_label = "未检查"
        session.token_status_message = "未设置 Token"
        session.last_error_text = ""
        session.connection_ok = False
        return [], "暂无", build_connection_status(session.token_status_message, "暂无", session.last_error_text), False

    def _run_refresh() -> tuple[list[dict], str, str, bool]:
        client = build_client_from_config(
            config,
            token,
            timeout=config.export_defaults.token_check_timeout,
            max_retries=1,
            rate_limit_backoff_seconds=0.0,
            network_backoff_seconds=0.0,
            max_backoff_seconds=0.0,
        )
        if client.proxy_enabled:
            proxy_ok, proxy_msg = client.test_proxy()
            if not proxy_ok:
                session.current_user_label = "未检查"
                session.token_status_message = f"代理连接失败：{proxy_msg}"
                session.last_error_text = proxy_msg
                session.connection_ok = False
                append_console_log(f"代理测试失败: {proxy_msg}")
                return [], "暂无", build_connection_status(session.token_status_message, "暂无", session.last_error_text), False
        user, repos = list_accessible_repos(client)
        login = user.get("login") or "unknown"
        session.current_user_label = f"{user.get('name') or login} ({login})"
        session.token_status_message = ""
        session.status_message = f"连接已刷新，可访问知识库 {len(repos)} 个"
        session.last_error_text = ""
        session.network_test_message = ""
        session.connection_ok = True
        rate_limit_summary = format_rate_limit(client.last_rate_limit)
        append_console_log(f"刷新连接成功: user={session.current_user_label}, repos={len(repos)}")
        return repos, rate_limit_summary, build_connection_status(session.status_message, rate_limit_summary, session.last_error_text), True

    try:
        if interactive:
            refresh_state = MenuRefreshState(lines=["正在检查 Token、当前用户和限流状态", "如遇语雀限流，将返回专门提示"])
            session.menu_refresh_state = refresh_state
            session.transient_lines = refresh_state.lines
            append_console_log("开始刷新连接状态")

            def _worker() -> None:
                try:
                    refresh_state.result = _run_refresh()
                except Exception as exc:  # noqa: BLE001
                    refresh_state.error = exc
                finally:
                    refresh_state.done = True

            worker = threading.Thread(target=_worker, daemon=True)
            worker.start()
            return [], "处理中", build_connection_status("正在检查 Token、当前用户和限流状态", "暂无", ""), False
        return _run_refresh()
    except YuqueRateLimitError as exc:
        session.current_user_label = "未检查"
        session.connection_ok = False
        session.last_error_text = format_error_detail(exc)
        wait_hint = f"建议等待 {int(exc.retry_after)} 秒后再试" if getattr(exc, "retry_after", None) else "建议稍后再试"
        session.token_status_message = f"触发语雀限流，{wait_hint}"
        append_console_log(f"刷新连接限流: {session.last_error_text}")
        return [], "429 LIMIT", build_connection_status(session.token_status_message, "429 LIMIT", session.last_error_text), False
    except Exception as exc:  # noqa: BLE001
        error_str = str(exc)
        proxy = config.export_defaults.proxy
        if proxy.enabled and proxy.host:
            client = build_client_from_config(config, token, timeout=config.export_defaults.token_check_timeout, max_retries=1)
            proxy_ok, proxy_msg = client.test_proxy()
            if not proxy_ok:
                session.current_user_label = "未检查"
                session.token_status_message = f"代理连接失败：{proxy_msg}"
                session.last_error_text = proxy_msg
                session.connection_ok = False
                append_console_log(f"刷新连接失败（代理问题）: {proxy_msg}")
                return [], "暂无", build_connection_status(session.token_status_message, "暂无", session.last_error_text), False
            session.current_user_label = "未检查"
            session.token_status_message = "连接检查失败（代理正常，请检查 Token 或网络）"
            session.last_error_text = error_str
            session.connection_ok = False
            append_console_log(f"刷新连接失败（API 问题）: {error_str}")
        else:
            session.current_user_label = "未检查"
            session.token_status_message = "连接检查失败"
            session.last_error_text = error_str
            session.connection_ok = False
            append_console_log(f"刷新连接失败: {error_str}")
        return [], "暂无", build_connection_status(session.token_status_message, "暂无", session.last_error_text), False
