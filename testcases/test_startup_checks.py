"""启动检查测试。"""

from __future__ import annotations

import importlib
import locale

import yuque2markdown


def test_check_runtime_support_reports_windows_unsupported(monkeypatch) -> None:
    monkeypatch.setattr(yuque2markdown.sys, "platform", "win32")

    message = yuque2markdown.check_runtime_support()

    assert message == "当前版本仅支持 macOS 运行"


def test_check_runtime_support_reports_non_macos_unsupported(monkeypatch) -> None:
    monkeypatch.setattr(yuque2markdown.sys, "platform", "win32")

    message = yuque2markdown.check_runtime_support()

    assert message == "当前版本仅支持 macOS 运行"


def test_check_runtime_support_reports_linux_unsupported(monkeypatch) -> None:
    monkeypatch.setattr(yuque2markdown.sys, "platform", "linux")

    message = yuque2markdown.check_runtime_support()

    assert message == "当前版本仅支持 macOS 运行"


def test_check_runtime_support_reports_missing_curses_on_macos(monkeypatch) -> None:
    original_import_module = importlib.import_module

    def fake_import_module(name: str):
        if name == "curses":
            raise ImportError("No module named '_curses'")
        return original_import_module(name)

    monkeypatch.setattr(yuque2markdown.sys, "platform", "darwin")
    monkeypatch.setattr(yuque2markdown.importlib, "import_module", fake_import_module)

    message = yuque2markdown.check_runtime_support()

    assert "windows-curses" not in message
    assert "No module named '_curses'" in message


def test_configure_console_locale_ignores_locale_error(monkeypatch) -> None:
    monkeypatch.setattr(yuque2markdown.locale, "setlocale", lambda *_args, **_kwargs: (_ for _ in ()).throw(locale.Error("boom")))

    yuque2markdown.configure_console_locale()
