from core_modules.export.errors import YuqueRateLimitError
from core_modules.version import APP_VERSION

from core_modules.auth.browser_cookies import BrowserCookieResult
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
from core_modules.export.models import ExportResult, RepoRef


def test_build_main_menu_items_hides_repo_actions_when_connection_invalid() -> None:
    config = AppConfig()
    session = SessionState()

    items = _build_main_menu_items(config, session, "暂无")
    keys = [item.key for item in items]
    auth_item = next(item for item in items if item.key == "auth_mode")

    assert auth_item.title == "登录方式: "
    assert [choice.label for choice in auth_item.inline_choices] == ["浏览器 Cookie", "Token"]
    assert keys.index("auth_mode") < keys.index("token")
    assert "token" in keys
    assert "import_cookie" not in keys
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


def test_build_main_menu_items_shows_cookie_action_only_in_cookie_mode() -> None:
    config = AppConfig(auth_mode="cookie")
    session = SessionState()

    items = _build_main_menu_items(config, session, "暂无")
    keys = [item.key for item in items]
    auth_item = next(item for item in items if item.key == "auth_mode")

    assert auth_item.title == "登录方式: "
    assert auth_item.inline_choices[0].checked is True
    assert keys.index("auth_mode") < keys.index("import_cookie")
    assert "import_cookie" in keys
    assert "token" not in keys


def test_build_main_menu_items_shows_cookie_source_from_config() -> None:
    config = AppConfig(auth_mode="cookie", cookie="demo-cookie")
    session = SessionState(cookie_source_label="配置文件")

    items = _build_main_menu_items(config, session, "暂无")
    import_item = next(item for item in items if item.key == "import_cookie")

    assert import_item.value == "已从配置文件加载，可从浏览器重新读取"


def test_build_main_menu_items_shows_cookie_source_from_browser() -> None:
    config = AppConfig(auth_mode="cookie", cookie="demo-cookie")
    session = SessionState(cookie_source_label="Chrome/Default")

    items = _build_main_menu_items(config, session, "暂无")
    import_item = next(item for item in items if item.key == "import_cookie")

    assert import_item.value == "已从浏览器加载（Chrome/Default），可重新读取"


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
    assert captured["status_lines"][0] == "[YELLOW] Token: 已加载 Token，请刷新连接状态"


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


def test_build_result_lines_uses_total_elapsed_and_omits_config_save() -> None:
    config = AppConfig()
    session = SessionState(repo_display_name="Android逆向学习", selected_doc_ids={1})
    result = ExportResult(
        repo=RepoRef(group_login="demo", book_slug="android", name="Android逆向学习"),
        exported_docs=1,
        skipped_docs=0,
        failed_docs=0,
        rewritten_links=0,
        total_downloaded=2,
        elapsed_seconds=31.3,
    )

    lines = _build_result_lines(config, session, result)

    assert "  总耗时: 31.3 秒" in lines
    assert "  知识库: Android逆向学习" in lines
    assert "  成功: 1 | 跳过: 0 | 失败: 0" in lines
    assert not any(line.startswith("配置保存:") for line in lines)


def test_run_console_app_imports_cookie_from_browser(monkeypatch) -> None:
    config = AppConfig()
    calls = {"count": 0}

    def fake_load_config() -> AppConfig:
        return config

    def fake_run_menu(title, items, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return "import_cookie"
        return "exit"

    def fake_persist_config(cfg, session, reason):
        assert reason == "cookie_imported"
        session.dirty = False
        return cfg

    monkeypatch.setattr("core_modules.console.app.load_config", fake_load_config)
    monkeypatch.setattr("core_modules.console.app.run_menu", fake_run_menu)
    monkeypatch.setattr(
        "core_modules.console.app.load_yuque_cookie_from_browsers",
        lambda: BrowserCookieResult("yuque_ctoken=demo", "Chrome/Default", "已加载"),
    )
    monkeypatch.setattr("core_modules.console.app._persist_config", fake_persist_config)

    assert run_console_app() == 0
    assert config.auth_mode == "cookie"
    assert config.cookie == "yuque_ctoken=demo"


def test_run_console_app_marks_cookie_as_loaded_from_config_on_startup(monkeypatch) -> None:
    config = AppConfig(auth_mode="cookie", cookie="yuque_ctoken=demo")
    captured: dict[str, object] = {}

    def fake_load_config() -> AppConfig:
        return config

    def fake_run_menu(title, items, **kwargs):
        captured["items"] = items
        return "exit"

    monkeypatch.setattr("core_modules.console.app.load_config", fake_load_config)
    monkeypatch.setattr("core_modules.console.app.run_menu", fake_run_menu)

    assert run_console_app() == 0
    import_item = next(item for item in captured["items"] if item.key == "import_cookie")
    assert import_item.value == "已从配置文件加载，可从浏览器重新读取"


def test_run_console_app_switching_to_cookie_imports_when_empty(monkeypatch) -> None:
    config = AppConfig()
    calls = {"count": 0}

    def fake_load_config() -> AppConfig:
        return config

    def fake_run_menu(title, items, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return "auth_mode_cookie"
        return "exit"

    monkeypatch.setattr("core_modules.console.app.load_config", fake_load_config)
    monkeypatch.setattr("core_modules.console.app.run_menu", fake_run_menu)
    monkeypatch.setattr(
        "core_modules.console.app.load_yuque_cookie_from_browsers",
        lambda: BrowserCookieResult("yuque_ctoken=demo", "Chrome/Default", "已加载"),
    )
    monkeypatch.setattr("core_modules.console.app._persist_config", lambda cfg, session, reason: cfg)

    assert run_console_app() == 0
    assert config.auth_mode == "cookie"
    assert config.cookie == "yuque_ctoken=demo"


def test_run_console_app_switching_cookie_to_token_keeps_focus_on_auth_mode(monkeypatch) -> None:
    config = AppConfig(auth_mode="cookie", cookie="yuque_ctoken=demo")
    calls = {"count": 0}
    captured_initial_indexes: list[int] = []
    captured_items: list[list] = []

    def fake_load_config() -> AppConfig:
        return config

    def fake_run_menu(title, items, **kwargs):
        captured_items.append(items)
        captured_initial_indexes.append(kwargs.get("initial_index", 0))
        calls["count"] += 1
        if calls["count"] == 1:
            return "refresh_connection"
        if calls["count"] == 2:
            return "auth_mode_token"
        return "exit"

    monkeypatch.setattr("core_modules.console.app.load_config", fake_load_config)
    monkeypatch.setattr("core_modules.console.app.run_menu", fake_run_menu)
    monkeypatch.setattr("core_modules.console.app._refresh_connection_state", lambda *args, **kwargs: None)
    monkeypatch.setattr("core_modules.console.app._persist_config", lambda cfg, session, reason: cfg)

    assert run_console_app() == 0
    assert config.auth_mode == "token"
    auth_index = next(index for index, item in enumerate(captured_items[2]) if item.key == "auth_mode")
    assert captured_initial_indexes[2] == auth_index


def test_run_console_app_switching_token_to_cookie_keeps_focus_on_auth_mode(monkeypatch) -> None:
    config = AppConfig(token="demo-token")
    calls = {"count": 0}
    captured_initial_indexes: list[int] = []
    captured_items: list[list] = []

    def fake_load_config() -> AppConfig:
        return config

    def fake_run_menu(title, items, **kwargs):
        captured_items.append(items)
        captured_initial_indexes.append(kwargs.get("initial_index", 0))
        calls["count"] += 1
        if calls["count"] == 1:
            return "refresh_connection"
        if calls["count"] == 2:
            return "auth_mode_cookie"
        return "exit"

    monkeypatch.setattr("core_modules.console.app.load_config", fake_load_config)
    monkeypatch.setattr("core_modules.console.app.run_menu", fake_run_menu)
    monkeypatch.setattr(
        "core_modules.console.app.load_yuque_cookie_from_browsers",
        lambda: BrowserCookieResult("yuque_ctoken=demo", "Chrome/Default", "已加载"),
    )
    monkeypatch.setattr("core_modules.console.app._refresh_connection_state", lambda *args, **kwargs: None)
    monkeypatch.setattr("core_modules.console.app._persist_config", lambda cfg, session, reason: cfg)

    assert run_console_app() == 0
    assert config.auth_mode == "cookie"
    auth_index = next(index for index, item in enumerate(captured_items[2]) if item.key == "auth_mode")
    assert captured_initial_indexes[2] == auth_index


def test_run_console_app_clear_token_clears_repo_context(monkeypatch) -> None:
    config = AppConfig(token="demo-token", cookie="yuque_ctoken=demo")
    calls = {"count": 0}
    captured_sessions: list[SessionState] = []

    def fake_load_config() -> AppConfig:
        return config

    def fake_run_menu(title, items, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return "clear_token"
        return "exit"

    def fake_persist_config(cfg, session, reason):
        if reason == "token_cleared":
            captured_sessions.append(session)
        return cfg

    monkeypatch.setattr("core_modules.console.app.load_config", fake_load_config)
    monkeypatch.setattr("core_modules.console.app.run_menu", fake_run_menu)
    monkeypatch.setattr("core_modules.console.app._persist_config", fake_persist_config)

    original_session_state = __import__("core_modules.console.app", fromlist=["SessionState"]).SessionState

    class PreparedSessionState(original_session_state):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.connection_ok = True
            self.current_user_login = "cyberangel"
            self.repo_input = "group/repo"
            self.repo_display_name = "测试库"
            self.repo_namespace = "group/repo"
            self.repo_url = "https://www.yuque.com/group/repo"
            self.repo_filter = "repo"
            self.repo_list_index = 3
            self.selected_doc_ids = {1, 2}
            self.selected_doc_count = 2

    monkeypatch.setattr("core_modules.console.app.SessionState", PreparedSessionState)

    assert run_console_app() == 0
    cleared = captured_sessions[0]
    assert cleared.current_user_login == ""
    assert cleared.repo_input == ""
    assert cleared.repo_display_name == ""
    assert cleared.repo_namespace == ""
    assert cleared.repo_url == ""
    assert cleared.repo_filter == ""
    assert cleared.repo_list_index == 0
    assert cleared.selected_doc_ids is None
    assert cleared.selected_doc_count == 0


def test_build_confirmation_lines_include_sections() -> None:
    config = AppConfig(token="demo-token", persist_token=True)
    session = SessionState(repo_display_name="测试库", repo_namespace="group/test", current_user_label="Demo User", dirty=True)

    lines = _build_confirmation_lines(config, session)

    assert "[连接与身份]" in lines
    assert "[知识库与范围]" in lines
    assert "[导出路径与资源]" in lines
    assert "[保存状态]" in lines
    assert any("Token" in line for line in lines)
