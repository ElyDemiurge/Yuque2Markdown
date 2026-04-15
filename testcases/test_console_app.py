from core_modules.export.errors import YuqueRateLimitError
from core_modules.version import APP_VERSION

from core_modules.config.models import AppConfig, SessionState
from core_modules.console.app import (
    _build_client_from_config,
    _build_confirmation_lines,
    _build_connection_status,
    _build_main_menu_items,
    _build_main_title,
    _build_result_lines,
    _build_status_detail,
    _parse_non_negative_float,
    _parse_optional_positive_int,
    _parse_positive_int,
    _refresh_connection_state,
    run_console_app,
)


def test_build_main_menu_items_hides_repo_actions_when_connection_invalid() -> None:
    config = AppConfig()
    session = SessionState()

    items = _build_main_menu_items(config, session, "暂无")
    keys = [item.key for item in items]

    assert "token" in keys
    assert "repo_input" not in keys
    assert "select_repo" not in keys
    assert "select_docs" not in keys
    assert "start_export" not in keys


def test_build_main_menu_items_adds_sections_and_readonly_not_focusable() -> None:
    config = AppConfig(token="demo-token")
    session = SessionState(connection_ok=True)

    items = _build_main_menu_items(config, session, "X-RateLimit-Limit=500")
    section_items = [item for item in items if item.item_type == "section"]
    readonly_items = [item for item in items if item.item_type == "readonly"]

    assert section_items
    assert readonly_items
    assert all(item.focusable is False for item in section_items)
    assert all(item.focusable is False for item in readonly_items)


def test_build_connection_status_omits_empty_rate_limit() -> None:
    assert _build_connection_status("未配置 token", "暂无") == "连接状态: 未配置 token"
    assert _build_connection_status("Token 心跳正常", "X-RateLimit-Limit=500") == "[GREEN] 连接状态: Token 心跳正常 | X-RateLimit-Limit=500"
    assert _build_connection_status("连接检查失败", "暂无", "boom") == "[RED] 连接状态: 连接检查失败 | error=boom"
    assert _build_status_detail("X-RateLimit-Limit=500", "") == "限流: X-RateLimit-Limit=500"
    assert _build_status_detail("暂无", "boom") == "详情: boom"


def test_build_connection_status_uses_severity_colors() -> None:
    assert _build_connection_status("触发语雀限流 (429)，建议等待 30 秒后再试", "429 LIMIT").startswith("[YELLOW]")
    assert _build_connection_status("连接检查失败: boom", "暂无").startswith("[RED]")
    assert _build_connection_status("正在检查 token", "暂无").startswith("[BLUE]")


def test_build_main_title_marks_dirty_state() -> None:
    assert _build_main_title(SessionState(dirty=False)) == f"Yuque2Markdown {APP_VERSION} 控制台"
    assert _build_main_title(SessionState(dirty=True)) == f"Yuque2Markdown {APP_VERSION} 控制台 [未保存]"


def test_parse_number_helpers_accept_valid_values() -> None:
    assert _parse_non_negative_float("0.1") == 0.1
    assert _parse_positive_int("3") == 3
    assert _parse_optional_positive_int("") is None


def test_build_client_from_config_allows_overrides() -> None:
    config = AppConfig()
    config.export_defaults.request_interval = 0.1
    config.export_defaults.timeout = 10
    config.export_defaults.request_max_retries = 5
    config.export_defaults.rate_limit_backoff_seconds = 5.0
    config.export_defaults.network_backoff_seconds = 2.0
    config.export_defaults.max_backoff_seconds = 60.0

    client = _build_client_from_config(
        config,
        "demo-token",
        timeout=3,
        max_retries=1,
        rate_limit_backoff_seconds=0.0,
        network_backoff_seconds=0.0,
        max_backoff_seconds=0.0,
    )

    assert client.timeout == 3
    assert client.request_interval == 0.1
    assert client.max_retries == 1
    assert client.rate_limit_backoff_seconds == 0.0
    assert client.network_backoff_seconds == 0.0
    assert client.max_backoff_seconds == 0.0


def test_refresh_connection_state_uses_fast_token_check_client(monkeypatch) -> None:
    config = AppConfig(token="demo-token")
    session = SessionState()
    captured: dict[str, object] = {}

    def fake_build_client_from_config(cfg, token, **kwargs):
        captured["token"] = token
        captured.update(kwargs)

        class DummyClient:
            last_rate_limit = {"limit": None, "remaining": None, "reset": None}

        return DummyClient()

    def fake_list_accessible_repos(client):
        return {"login": "demo", "name": "Demo"}, []

    monkeypatch.setattr("core_modules.console.app._build_client_from_config", fake_build_client_from_config)
    monkeypatch.setattr("core_modules.console.app.list_accessible_repos", fake_list_accessible_repos)

    _refresh_connection_state("demo-token", config, session, interactive=False)

    assert captured["token"] == "demo-token"
    assert captured["timeout"] == config.export_defaults.token_check_timeout
    assert captured["max_retries"] == 1
    assert captured["rate_limit_backoff_seconds"] == 0.0
    assert captured["network_backoff_seconds"] == 0.0
    assert captured["max_backoff_seconds"] == 0.0


def test_run_console_app_does_not_refresh_connection_on_startup(monkeypatch) -> None:
    config = AppConfig(token="demo-token")
    captured: dict[str, object] = {}

    def fake_load_config() -> AppConfig:
        return config

    def fake_run_menu(title, items, **kwargs):
        captured["title"] = title
        captured["status_lines"] = kwargs.get("status_lines")
        return "exit"

    def fake_refresh_connection_state(*args, **kwargs):
        raise AssertionError("startup should not refresh connection")

    monkeypatch.setattr("core_modules.console.app.load_config", fake_load_config)
    monkeypatch.setattr("core_modules.console.app.run_menu", fake_run_menu)
    monkeypatch.setattr("core_modules.console.app._refresh_connection_state", fake_refresh_connection_state)

    assert run_console_app() == 0
    assert captured["title"] == f"Yuque2Markdown {APP_VERSION} 控制台"
    assert isinstance(captured["status_lines"], list)
    assert captured["status_lines"][0] == "[YELLOW] Token: 已加载 Token，请刷新 Token 状态"


def test_run_console_app_handles_refresh_rate_limit_without_crashing(monkeypatch) -> None:
    config = AppConfig(token="demo-token")
    session_state = {"calls": 0}

    def fake_load_config() -> AppConfig:
        return config

    def fake_run_menu(title, items, **kwargs):
        session_state["calls"] += 1
        refresh_state = kwargs.get("refresh_state")
        if session_state["calls"] == 1:
            return "refresh_connection"
        if refresh_state is not None:
            refresh_state.error = YuqueRateLimitError("Too Many Requests", retry_after=1)
            refresh_state.done = True
            return "__refresh_done__"
        return "exit"

    monkeypatch.setattr("core_modules.console.app.load_config", fake_load_config)
    monkeypatch.setattr("core_modules.console.app.run_menu", fake_run_menu)
    monkeypatch.setattr("core_modules.console.app._refresh_connection_state", lambda *args, **kwargs: None)

    assert run_console_app() == 0


def test_build_confirmation_lines_include_sections() -> None:
    config = AppConfig(token="demo-token", persist_token=True)
    session = SessionState(repo_display_name="测试库", repo_namespace="group/test", current_user_label="Demo User", dirty=True)

    lines = _build_confirmation_lines(config, session)

    assert "[连接与身份]" in lines
    assert "[知识库与范围]" in lines
    assert "[导出路径与资源]" in lines
    assert "[保存状态]" in lines
    assert any("Token" in line for line in lines)
