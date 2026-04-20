from __future__ import annotations

from datetime import datetime
from pathlib import Path

from core_modules.config.models import (
    AUTH_MODE_COOKIE,
    AUTH_MODE_TOKEN,
    AppConfig,
    SessionState,
    active_auth_value,
    auth_mode_label,
    normalize_auth_mode,
)
from core_modules.config.store import load_config
from core_modules.browser_cookies import load_yuque_cookie_from_browsers
from core_modules.console.helpers import parse_action
from core_modules.console.menu import InlineChoice, MenuItem, run_menu, show_message
from core_modules.export.cli import build_client
from core_modules.export.cli import list_accessible_repos
from core_modules.export.errors import YuqueRateLimitError
from core_modules.version import APP_VERSION


MAIN_MENU_KEY = "main"
EXPORT_SETTINGS_MENU_KEY = "export_settings"
RUNTIME_SETTINGS_MENU_KEY = "runtime_settings"
ADVANCED_SETTINGS_MENU_KEY = "advanced_settings"


def run_console_app() -> int:
    """运行控制台主循环并处理用户操作。"""
    config = load_config()
    session = SessionState(repo_input=config.last_repo_input)
    rate_limit_summary = "暂无"
    repos: list[dict] = []
    _append_console_log("进入控制台")

    config.auth_mode = normalize_auth_mode(config.auth_mode)
    credential = active_auth_value(config)
    if credential:
        config.token = (config.token or "").strip()
        config.cookie = (config.cookie or "").strip()
        session.token_status_message = f"已加载 {auth_mode_label(config.auth_mode)}，请刷新连接状态"
    else:
        session.token_status_message = f"未设置 {auth_mode_label(config.auth_mode)}"

    while True:
        title = _build_main_title(session)
        items = _build_main_menu_items(config, session, rate_limit_summary)
        status_lines = _build_status_lines(config, session, rate_limit_summary)
        action = run_menu(
            title,
            items,
            status_lines=status_lines,
            initial_index=session.menu_index_map.get(MAIN_MENU_KEY, 0),
            transient_lines=session.transient_lines if session.menu_refresh_state is not None else None,
            refresh_state=session.menu_refresh_state,
        )
        if action is None or action == "exit":
            _append_console_log("退出控制台")
            if session.dirty and config.ui_preferences.auto_save_after_export:
                config = _persist_config(config, session, "on_exit")
            return 0
        if action == "__refresh_done__":
            state = session.menu_refresh_state
            session.menu_refresh_state = None
            session.transient_lines = []
            if state is not None:
                state.done = True
                state.lines = []
            if state is not None and state.error is not None:
                if isinstance(state.error, YuqueRateLimitError):
                    wait_hint = (
                        f"建议等待 {int(state.error.retry_after)} 秒后再试"
                        if getattr(state.error, "retry_after", None)
                        else "建议稍后再试"
                    )
                    session.current_user_label = "未检查"
                    session.connection_ok = False
                    session.token_status_message = f"触发语雀限流，{wait_hint}"
                    session.last_error_text = _format_error_detail(state.error)
                    rate_limit_summary = "429 LIMIT"
                else:
                    session.current_user_label = "未检查"
                    session.connection_ok = False
                    session.token_status_message = "连接检查失败"
                    session.last_error_text = _format_error_detail(state.error)
                    rate_limit_summary = "暂无"
                continue
            if state is not None and state.result is not None:
                repos, rate_limit_summary, _, session.connection_ok = state.result
            continue
        key, edited_value = parse_action(action)
        _remember_menu_index(session, MAIN_MENU_KEY, items, key)
        if key == "refresh_connection":
            _refresh_connection_state(active_auth_value(config), config, session, interactive=True)
            continue
        if key in {"auth_mode_token", "auth_mode_cookie"}:
            new_mode = AUTH_MODE_COOKIE if key == "auth_mode_cookie" else AUTH_MODE_TOKEN
            if config.auth_mode != new_mode:
                config.auth_mode = new_mode
                session.connection_ok = False
                session.current_user_label = "未检查"
                session.last_error_text = ""
                session.network_test_message = ""
                session.token_status_message = f"已切换为 {auth_mode_label(new_mode)} 登录，请刷新连接状态"
                if new_mode == AUTH_MODE_COOKIE and not (config.cookie or "").strip():
                    result = load_yuque_cookie_from_browsers()
                    if result.ok:
                        config.cookie = result.cookie
                        config.persist_cookie = True
                        session.token_status_message = f"{result.message}，请刷新连接状态"
                    else:
                        session.token_status_message = result.message
                        show_message("读取 Cookie 失败", [result.message])
                session.dirty = True
                repos = []
                rate_limit_summary = "暂无"
                config = _persist_config(config, session, "auth_mode_changed")
            continue
        if key == "token":
            if edited_value is not None:
                config.token = edited_value.strip()
                session.connection_ok = False
                session.network_test_message = ""  # 清空网络测试结果
                session.last_error_text = ""  # 清空错误详情
                if config.token:
                    session.token_status_message = "已重新设置 Token，请刷新连接状态"
                else:
                    session.token_status_message = "Token 已清空"
                session.dirty = True
                config = _persist_config(config, session, "token_changed")
            repos = []
            rate_limit_summary = "暂无"
            session.connection_ok = False
            continue
        if key == "import_cookie":
            result = load_yuque_cookie_from_browsers()
            if result.ok:
                config.auth_mode = AUTH_MODE_COOKIE
                config.cookie = result.cookie
                config.persist_cookie = True
                session.connection_ok = False
                session.current_user_label = "未检查"
                session.last_error_text = ""
                session.network_test_message = ""
                session.token_status_message = f"{result.message}，请刷新连接状态"
                session.dirty = True
                repos = []
                rate_limit_summary = "暂无"
                config = _persist_config(config, session, "cookie_imported")
            else:
                session.token_status_message = result.message
                show_message("读取 Cookie 失败", [result.message])
            continue
        if key == "clear_token":
            config.token = ""
            config.cookie = ""
            session.current_user_label = "未检查"
            session.token_status_message = "登录凭据已清空"
            session.connection_ok = False
            session.repo_display_name = ""
            session.repo_namespace = ""
            session.repo_url = ""
            repos = []
            rate_limit_summary = "暂无"
            session.dirty = True
            config = _persist_config(config, session, "token_cleared")
            continue
        if key == "repo_input" and edited_value is not None:
            if edited_value and _handle_repo_input_inline(config, session, edited_value):
                config = _persist_config(config, session, "repo_input")
            continue
        if key == "select_repo":
            if _handle_repo_selection(config, session, repos, rate_limit_summary):
                config = _persist_config(config, session, "repo_selected")
            continue
        if key == "export_settings":
            if _run_export_settings_menu(config, session):
                config = _persist_config(config, session, "export_settings")
            continue
        if key == "runtime_settings":
            if _run_runtime_settings_menu(config, session):
                config = _persist_config(config, session, "runtime_settings")
            continue
        if key == "advanced_settings":
            if _run_advanced_settings_menu(config, session):
                config = _persist_config(config, session, "advanced_settings")
            continue
        if key == "select_docs":
            rate_limit_summary, changed = _handle_doc_selection(config, session, rate_limit_summary)
            if changed:
                config = _persist_config(config, session, "doc_selection")
            continue
        if key == "save":
            config = _persist_config(config, session, "manual")
            continue
        if key == "last_export":
            if session.last_exported_docs and session.last_result_summary:
                show_message("上次导出结果", session.last_result_summary)
            else:
                show_message("上次导出结果", ["无导出记录"])
            continue
        if key == "start_export":
            rate_limit_summary = _handle_export(config, session, rate_limit_summary)
            continue


def _build_client_from_config(
    config: AppConfig,
    credential: str,
    *,
    timeout: int | None = None,
    max_retries: int | None = None,
    rate_limit_backoff_seconds: float | None = None,
    network_backoff_seconds: float | None = None,
    max_backoff_seconds: float | None = None,
):
    defaults = config.export_defaults
    proxy = defaults.proxy
    proxy_host = proxy.host or None if proxy.enabled else None
    auth_mode = normalize_auth_mode(config.auth_mode)
    token = credential if auth_mode == AUTH_MODE_TOKEN else (config.token or "").strip()
    cookie = credential if auth_mode == AUTH_MODE_COOKIE else (config.cookie or "").strip()
    return build_client(
        token,
        cookie=cookie,
        auth_mode=auth_mode,
        request_interval=defaults.request_interval,
        timeout=defaults.timeout if timeout is None else timeout,
        max_retries=defaults.request_max_retries if max_retries is None else max_retries,
        rate_limit_backoff_seconds=defaults.rate_limit_backoff_seconds if rate_limit_backoff_seconds is None else rate_limit_backoff_seconds,
        network_backoff_seconds=defaults.network_backoff_seconds if network_backoff_seconds is None else network_backoff_seconds,
        max_backoff_seconds=defaults.max_backoff_seconds if max_backoff_seconds is None else max_backoff_seconds,
        proxy_host=proxy_host,
        proxy_port=proxy.port,
        proxy_test_url=proxy.test_url,
    )


def _handle_repo_input_inline(config: AppConfig, session: SessionState, value: str) -> bool:
    from core_modules.console.handlers.repo import handle_repo_input_inline as _handler
    return _handler(config, session, value, build_client_from_config=_build_client_from_config)


def _handle_repo_selection(config: AppConfig, session: SessionState, repos: list[dict], rate_limit_summary: str) -> bool:
    from core_modules.console.handlers.repo import handle_repo_selection as _handler
    return _handler(config, session, repos, rate_limit_summary, build_client_from_config=_build_client_from_config)


def _handle_doc_selection(config: AppConfig, session: SessionState, rate_limit_summary: str) -> tuple[str, bool]:
    from core_modules.console.handlers.repo import handle_doc_selection as _handler
    return _handler(config, session, rate_limit_summary, build_client_from_config=_build_client_from_config)


def _handle_export(config: AppConfig, session: SessionState, rate_limit_summary: str) -> str:
    from core_modules.console.handlers.export import handle_export as _handler
    return _handler(
        config,
        session,
        rate_limit_summary,
        build_client_from_config=_build_client_from_config,
        apply_session_to_config=_apply_session_to_config,
        persist_config=_persist_config,
        append_console_log=_append_console_log,
        build_selected_docs_text=_build_selected_docs_text,
        build_confirmation_lines=_build_confirmation_lines,
        build_result_lines=_build_result_lines,
        format_error_detail=_format_error_detail,
        format_rate_limit=_format_rate_limit,
    )


def _run_export_settings_menu(config: AppConfig, session: SessionState) -> bool:
    from core_modules.console.controllers.export_settings import ExportSettingsController

    controller = ExportSettingsController(config, session, status_lines_builder=_build_submenu_status_lines)
    return controller.run()


def _run_runtime_settings_menu(config: AppConfig, session: SessionState) -> bool:
    from core_modules.console.controllers.runtime_settings import RuntimeSettingsController
    controller = RuntimeSettingsController(config, session, status_lines_builder=_build_submenu_status_lines)
    return controller.run()


def _persist_config(config: AppConfig, session: SessionState, reason: str) -> AppConfig:
    from core_modules.console.handlers.config import persist_config
    return persist_config(config, session, reason, append_console_log=_append_console_log)


def _build_main_title(session: SessionState) -> str:
    base = f"Yuque2Markdown {APP_VERSION} 控制台"
    return f"{base} [未保存]" if session.dirty else base


def _build_main_menu_items(config: AppConfig, session: SessionState, rate_limit_summary: str) -> list[MenuItem]:
    has_token = bool((config.token or "").strip())
    has_cookie = bool((config.cookie or "").strip())
    auth_mode = normalize_auth_mode(config.auth_mode)
    items = [
        MenuItem("connection_section", "── 连接 ──", item_type="section", focusable=False),
        MenuItem("current_user", "当前用户", session.current_user_label if session.connection_ok else "未登录", item_type="readonly", focusable=False),
        MenuItem(
            "auth_mode",
            "登录方式: ",
            inline_choices=[
                InlineChoice("auth_mode_cookie", "浏览器 Cookie", checked=auth_mode == AUTH_MODE_COOKIE),
                InlineChoice("auth_mode_token", "Token", checked=auth_mode == AUTH_MODE_TOKEN),
            ],
            inline_selected_index=0 if auth_mode == AUTH_MODE_COOKIE else 1,
        ),
        MenuItem("refresh_connection", f"刷新 {auth_mode_label(auth_mode)} 状态", item_type="action"),
        MenuItem("clear_token", "清空登录凭据", item_type="action"),
        MenuItem("repo_section", "── 知识库与文档 ──", item_type="section", focusable=False),
    ]
    if auth_mode == AUTH_MODE_TOKEN:
        items.insert(3, MenuItem("token", "设置 Token", _mask_token(config.token) if has_token else "未设置", input_style=True, edit_value=config.token or ""))
    else:
        items.insert(3, MenuItem("import_cookie", "从浏览器或配置文件加载 Cookie", "已加载" if has_cookie else "未加载", item_type="action"))
    if session.connection_ok:
        repo_display = session.repo_namespace or session.repo_input or config.last_repo_input
        items.extend(
            [
                MenuItem("repo_input", "知识库", repo_display or "未设置", input_style=True, edit_value=repo_display or ""),
                MenuItem("select_repo", "从列表选择知识库", item_type="submenu"),
                MenuItem("select_docs", "选择文档", _build_selected_docs_text(session)),
            ]
        )
    else:
        items.append(MenuItem("repo_empty", "当前未连接，设置有效 Token 或 Cookie 后可选择知识库", item_type="readonly", focusable=False))
    items.extend(
        [
            MenuItem("export_section", "── 导出配置 ──", item_type="section", focusable=False),
            MenuItem("export_settings", "导出路径与资源", item_type="submenu"),
            MenuItem("runtime_settings", "运行与网络设置", item_type="submenu"),
            MenuItem("advanced_settings", "网络与代理", item_type="submenu"),
            MenuItem("action_section", "── 操作 ──", item_type="section", focusable=False),
            MenuItem("last_export", "上次导出结果", f"成功 {session.last_exported_docs} 篇" if session.last_exported_docs else "无导出记录", item_type="action"),
        ]
    )
    if session.connection_ok:
        items.append(MenuItem("start_export", "开始导出"))
    items.append(MenuItem("exit", "退出"))
    return items


def _run_advanced_settings_menu(config: AppConfig, session: SessionState) -> bool:
    from core_modules.console.controllers.advanced_settings import AdvancedSettingsController

    controller = AdvancedSettingsController(
        config,
        session,
        build_client_from_config=_build_client_from_config,
        status_lines_builder=_build_submenu_status_lines,
    )
    return controller.run()


def _build_confirmation_lines(config: AppConfig, session: SessionState) -> list[str]:
    from core_modules.console.state.view import build_confirmation_lines
    return build_confirmation_lines(config, session, build_selected_docs_text=_build_selected_docs_text)


def _build_result_lines(config: AppConfig, session: SessionState, result) -> list[str]:
    from core_modules.console.state.view import build_result_lines
    return build_result_lines(config, session, result, build_selected_docs_text=_build_selected_docs_text)


def _build_status_lines(config: AppConfig, session: SessionState, rate_limit_summary: str) -> list[str]:
    from core_modules.console.state.view import build_status_lines
    return build_status_lines(config, session, rate_limit_summary)


def _build_submenu_status_lines(config: AppConfig, session: SessionState) -> list[str]:
    """子菜单底部状态栏，与主界面保持一致。"""
    return _build_status_lines(config, session, "暂无")


def _build_selected_docs_text(session: SessionState) -> str:
    from core_modules.console.state.manager import build_selected_docs_text
    return build_selected_docs_text(session)


def _mask_token(token: str) -> str:
    from core_modules.console.state.view import mask_token
    return mask_token(token)


def _remember_menu_index(session: SessionState, menu_key: str, items: list[MenuItem], action: str) -> None:
    from core_modules.console.state.manager import remember_menu_index
    remember_menu_index(session, menu_key, items, action)


def _bool_text(value: bool) -> str:
    from core_modules.console.state.view import bool_text
    return bool_text(value)


def _apply_session_to_config(config: AppConfig, session: SessionState) -> AppConfig:
    from core_modules.console.handlers.config import apply_session_to_config
    return apply_session_to_config(config, session)


def _refresh_connection_state(token: str, config: AppConfig, session: SessionState, interactive: bool = False) -> tuple[list[dict], str, str, bool]:
    from core_modules.console.handlers.connection import refresh_connection_state

    return refresh_connection_state(
        token,
        config,
        session,
        build_client_from_config=_build_client_from_config,
        build_connection_status=_build_connection_status,
        format_rate_limit=_format_rate_limit,
        format_error_detail=_format_error_detail,
        append_console_log=_append_console_log,
        interactive=interactive,
    )


def _append_console_log(message: str) -> None:
    path = Path.cwd() / "yuque2markdown.console.log"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp}] {message}\n")


def _build_status_detail(rate_limit_summary: str, error_text: str) -> str:
    if error_text:
        return f"详情: {_dedupe_error_text('', error_text)}"
    if rate_limit_summary and rate_limit_summary != "暂无" and rate_limit_summary != "429 LIMIT":
        return f"限流: {rate_limit_summary}"
    return ""


def _dedupe_error_text(status_message: str, error_text: str) -> str:
    from core_modules.console.state.view import dedupe_error_text
    return dedupe_error_text(status_message, error_text)


def _parse_non_negative_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        show_message("输入无效", ["请求间隔必须是数字，例如 0.1 或 1。"])
        return None
    if parsed < 0:
        show_message("输入无效", ["请求间隔不能小于 0。"])
        return None
    return parsed


def _parse_positive_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        show_message("输入无效", ["请输入正整数。"])
        return None
    if parsed < 1:
        show_message("输入无效", ["请输入大于等于 1 的整数。"])
        return None
    return parsed


def _parse_optional_positive_int(value: str | None) -> int | None:
    if value is None:
        return None
    if not value.strip():
        return None
    return _parse_positive_int(value)


def _format_rate_limit(rate_limit: dict[str, str | int | None]) -> str:
    from core_modules.console.state.view import format_rate_limit
    return format_rate_limit(rate_limit)


def _build_connection_status(status_message: str, rate_limit_summary: str, error_text: str = "") -> str:
    from core_modules.console.state.view import build_connection_status
    return build_connection_status(status_message, rate_limit_summary, error_text)


def _format_error_detail(exc: Exception) -> str:
    from core_modules.console.handlers.error_handler import format_error_detail
    return format_error_detail(exc)
