"""控制台导出处理测试。"""

from core_modules.config.models import AppConfig, SessionState
from core_modules.console.handlers.export import handle_export


class _DummyClient:
    last_rate_limit = {"limit": None, "remaining": None, "reset": None}

    def __init__(self) -> None:
        self.cancel_event = None

    def set_cancel_event(self, event) -> None:
        self.cancel_event = event


class _InterruptingProgressUI:
    """模拟导出过程中触发 Ctrl+C，并检查确认框按钮文案。"""

    def run(self, worker, *, on_interrupt=None, on_complete=None):
        assert on_interrupt is not None
        confirmed = on_interrupt()
        assert confirmed is True
        raise KeyboardInterrupt


class _SuccessfulProgressUI:
    def run(self, worker, *, on_interrupt=None, on_complete=None):
        assert on_interrupt is not None
        result = worker()
        if on_complete is not None:
            on_complete(result)
        return result


def test_handle_export_interrupt_confirmation_uses_clear_labels(monkeypatch) -> None:
    config = AppConfig(token="demo-token")
    config.ui_preferences.confirm_before_export = False
    session = SessionState(connection_ok=True, repo_input="cyberangel/demo")
    captured: dict[str, object] = {}

    def fake_run_confirmation(title, lines, help_lines=None, confirm_label="确认导出", cancel_label="取消"):
        captured["title"] = title
        captured["lines"] = lines
        captured["help_lines"] = help_lines
        captured["confirm_label"] = confirm_label
        captured["cancel_label"] = cancel_label
        return True

    monkeypatch.setattr("core_modules.console.handlers.export.run_confirmation", fake_run_confirmation)
    monkeypatch.setattr("core_modules.console.handlers.export.ExportProgressUI", _InterruptingProgressUI)
    monkeypatch.setattr("core_modules.console.handlers.export.show_message", lambda *_args, **_kwargs: None)
    client = _DummyClient()

    result = handle_export(
        config,
        session,
        "暂无",
        build_client_from_config=lambda *_args, **_kwargs: client,
        apply_session_to_config=lambda cfg, _session: cfg,
        persist_config=lambda cfg, _session, _reason: cfg,
        append_console_log=lambda _message: None,
        build_selected_docs_text=lambda _session: "全部文档",
        build_confirmation_lines=lambda _config, _session: [],
        build_result_lines=lambda _config, _session, _result: [],
        format_error_detail=lambda exc: str(exc),
        format_rate_limit=lambda _rate_limit: "暂无",
    )

    assert result == "暂无"
    assert client.cancel_event is not None and client.cancel_event.is_set() is True
    assert captured["title"] == "确认退出导出"
    assert captured["confirm_label"] == "退出导出"
    assert captured["cancel_label"] == "继续导出"
    assert captured["help_lines"] is None


def test_handle_export_keeps_success_summary_in_progress_ui(monkeypatch) -> None:
    config = AppConfig(token="demo-token")
    config.ui_preferences.confirm_before_export = False
    session = SessionState(connection_ok=True, repo_input="cyberangel/demo")
    shown: list[tuple] = []

    class _Result:
        exported_docs = 2
        skipped_docs = 1
        failed_docs = 0

    monkeypatch.setattr("core_modules.console.handlers.export.ExportProgressUI", _SuccessfulProgressUI)
    monkeypatch.setattr("core_modules.console.handlers.export.show_message", lambda *args, **kwargs: shown.append((args, kwargs)))
    monkeypatch.setattr("core_modules.console.handlers.export.execute_export", lambda *_args, **_kwargs: _Result())

    result = handle_export(
        config,
        session,
        "暂无",
        build_client_from_config=lambda *_args, **_kwargs: _DummyClient(),
        apply_session_to_config=lambda cfg, _session: cfg,
        persist_config=lambda cfg, _session, _reason: cfg,
        append_console_log=lambda _message: None,
        build_selected_docs_text=lambda _session: "全部文档",
        build_confirmation_lines=lambda _config, _session: [],
        build_result_lines=lambda _config, _session, _result: ["[导出结果]", "成功: 2 | 跳过: 1 | 失败: 0"],
        format_error_detail=lambda exc: str(exc),
        format_rate_limit=lambda _rate_limit: "暂无",
    )

    assert result == "暂无"
    assert session.last_result_summary == ["[导出结果]", "成功: 2 | 跳过: 1 | 失败: 0"]
    assert shown == []
