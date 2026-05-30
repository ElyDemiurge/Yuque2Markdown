"""浏览器 Cookie 读取测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from core_modules.auth.browser_cookies import (
    BrowserCookieSource,
    default_chromium_sources,
    _decode_decrypted_cookie,
    _encrypted_cookie_failure_message,
    _read_cookies,
    load_yuque_cookie_from_browsers,
    supports_browser_cookie_import,
)


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

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("core_modules.auth.browser_cookies._get_safe_storage_password", lambda _service: b"password")
    monkeypatch.setattr("core_modules.auth.browser_cookies._decrypt_macos_chromium_cookie", lambda *_args, **_kwargs: "session-value")

    result = load_yuque_cookie_from_browsers(sources=[BrowserCookieSource("Chrome", tmp_path / "Chrome", "Chrome Safe Storage")])

    assert result.ok is True
    assert result.cookie == "_yuque_session=session-value"


def test_default_chromium_sources_returns_no_windows_sources(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Windows")

    assert default_chromium_sources(tmp_path) == []


def test_supports_browser_cookie_import_only_on_macos() -> None:
    assert supports_browser_cookie_import("Darwin") is True
    assert supports_browser_cookie_import("Windows") is False


def test_load_yuque_cookie_reports_missing_database(tmp_path: Path) -> None:
    result = load_yuque_cookie_from_browsers(sources=[BrowserCookieSource("Chrome", tmp_path / "Chrome", "Chrome Safe Storage")])

    assert result.ok is False
    assert "未找到" in result.message


def test_read_cookies_closes_copied_database_before_temp_cleanup(tmp_path: Path) -> None:
    cookie_db = tmp_path / "Chrome" / "Default" / "Network" / "Cookies"
    _create_cookie_db(cookie_db, [(".yuque.com", "yuque_ctoken", "token-value", b"", 0)])

    cookies, encrypted_count = _read_cookies(
        cookie_db,
        domain="yuque.com",
        safe_storage_password=None,
    )

    assert cookies == [("yuque_ctoken", "token-value")]
    assert encrypted_count == 0


def test_decode_decrypted_cookie_strips_chromium_host_hash() -> None:
    import hashlib

    host_key = ".yuque.com"
    raw = hashlib.sha256(host_key.encode("utf-8")).digest() + b"session-value"

    assert _decode_decrypted_cookie(raw, host_key=host_key) == "session-value"
