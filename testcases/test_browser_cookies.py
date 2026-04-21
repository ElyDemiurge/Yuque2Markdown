"""浏览器 Cookie 读取测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core_modules.auth.browser_cookies import BrowserCookieSource, load_yuque_cookie_from_browsers


def _create_cookie_db(path: Path, rows: list[tuple[str, str, str, bytes, int]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE cookies (
                host_key TEXT,
                name TEXT,
                value TEXT,
                encrypted_value BLOB,
                path TEXT,
                expires_utc INTEGER
            )
            """
        )
        conn.executemany(
            "INSERT INTO cookies (host_key, name, value, encrypted_value, path, expires_utc) VALUES (?, ?, ?, ?, '/', ?)",
            rows,
        )


def test_load_yuque_cookie_from_browser_plain_value(tmp_path: Path) -> None:
    cookie_db = tmp_path / "Chrome" / "Default" / "Network" / "Cookies"
    _create_cookie_db(
        cookie_db,
        [
            (".yuque.com", "yuque_ctoken", "token-value", b"", 0),
            ("www.yuque.com", "_yuque_session", "session-value", b"", 0),
            (".example.com", "ignored", "ignored", b"", 0),
        ],
    )

    result = load_yuque_cookie_from_browsers(sources=[BrowserCookieSource("Chrome", tmp_path / "Chrome", "Chrome Safe Storage")])

    assert result.ok is True
    assert "yuque_ctoken=token-value" in result.cookie
    assert "_yuque_session=session-value" in result.cookie
    assert "ignored" not in result.cookie
    assert result.source == "Chrome/Default"


def test_load_yuque_cookie_keeps_same_name_for_different_hosts(tmp_path: Path) -> None:
    cookie_db = tmp_path / "Chrome" / "Default" / "Network" / "Cookies"
    _create_cookie_db(
        cookie_db,
        [
            (".yuque.com", "same_name", "root-value", b"", 0),
            ("www.yuque.com", "same_name", "www-value", b"", 0),
        ],
    )

    result = load_yuque_cookie_from_browsers(sources=[BrowserCookieSource("Chrome", tmp_path / "Chrome", "Chrome Safe Storage")])

    assert result.ok is True
    assert "same_name=root-value" in result.cookie
    assert "same_name=www-value" in result.cookie


def test_load_yuque_cookie_reports_encrypted_values_without_key(tmp_path: Path) -> None:
    cookie_db = tmp_path / "Chrome" / "Default" / "Network" / "Cookies"
    _create_cookie_db(cookie_db, [(".yuque.com", "_yuque_session", "", b"v10encrypted", 0)])

    result = load_yuque_cookie_from_browsers(sources=[BrowserCookieSource("Chrome", tmp_path / "Chrome", "Chrome Safe Storage")])

    assert result.ok is False
    assert "无法解密" in result.message


def test_load_yuque_cookie_uses_decrypted_value(tmp_path: Path, monkeypatch) -> None:
    cookie_db = tmp_path / "Chrome" / "Default" / "Network" / "Cookies"
    _create_cookie_db(cookie_db, [(".yuque.com", "_yuque_session", "", b"v10encrypted", 0)])

    monkeypatch.setattr("core_modules.auth.browser_cookies._get_safe_storage_password", lambda _service: b"password")
    monkeypatch.setattr("core_modules.auth.browser_cookies._decrypt_macos_chromium_cookie", lambda *_args, **_kwargs: "session-value")

    result = load_yuque_cookie_from_browsers(sources=[BrowserCookieSource("Chrome", tmp_path / "Chrome", "Chrome Safe Storage")])

    assert result.ok is True
    assert result.cookie == "_yuque_session=session-value"


def test_load_yuque_cookie_reports_missing_database(tmp_path: Path) -> None:
    result = load_yuque_cookie_from_browsers(sources=[BrowserCookieSource("Chrome", tmp_path / "Chrome", "Chrome Safe Storage")])

    assert result.ok is False
    assert "未找到" in result.message


def test_load_yuque_cookie_uses_windows_decryptor(tmp_path: Path, monkeypatch) -> None:
    cookie_db = tmp_path / "Chrome" / "Default" / "Network" / "Cookies"
    _create_cookie_db(cookie_db, [(".yuque.com", "_yuque_session", "", b"v10encrypted", 0)])

    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr("core_modules.auth.browser_cookies._get_windows_chromium_key", lambda _root: b"windows-key")
    monkeypatch.setattr("core_modules.auth.browser_cookies._decrypt_windows_chromium_cookie", lambda *_args, **_kwargs: "session-value")

    result = load_yuque_cookie_from_browsers(sources=[BrowserCookieSource("Chrome", tmp_path / "Chrome", "")])

    assert result.ok is True
    assert result.cookie == "_yuque_session=session-value"
