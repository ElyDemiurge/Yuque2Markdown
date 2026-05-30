"""从本机浏览器读取语雀 Cookie。"""

from __future__ import annotations

import hashlib
import platform
import shutil
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path


CHROME_EPOCH_OFFSET_SECONDS = 11644473600
YUQUE_COOKIE_DOMAIN = "yuque.com"


@dataclass(slots=True)
class BrowserCookieSource:
    """一个浏览器 Cookie 存储位置。"""

    name: str
    profile_root: Path
    safe_storage_service: str


@dataclass(slots=True)
class BrowserCookieResult:
    """浏览器 Cookie 读取结果。"""

    cookie: str
    source: str
    message: str

    @property
    def ok(self) -> bool:
        return bool(self.cookie)


def supports_browser_cookie_import(system_name: str | None = None) -> bool:
    """平台是否支持读取 Chromium 浏览器 Cookie。"""
    return (system_name or platform.system()) == "Darwin"


def default_chromium_sources(home: Path | None = None) -> list[BrowserCookieSource]:
    """返回常见 Chromium 系浏览器的 Cookie 目录。"""

    root = home or Path.home()
    if not supports_browser_cookie_import():
        return []
    app_support = root / "Library" / "Application Support"
    return [
        BrowserCookieSource("Chrome", app_support / "Google" / "Chrome", "Chrome Safe Storage"),
        BrowserCookieSource("Edge", app_support / "Microsoft Edge", "Microsoft Edge Safe Storage"),
        BrowserCookieSource("Brave", app_support / "BraveSoftware" / "Brave-Browser", "Brave Safe Storage"),
        BrowserCookieSource("Chromium", app_support / "Chromium", "Chromium Safe Storage"),
    ]


def load_yuque_cookie_from_browsers(
    *,
    sources: list[BrowserCookieSource] | None = None,
    domain: str = YUQUE_COOKIE_DOMAIN,
) -> BrowserCookieResult:
    """从浏览器中读取语雀 Cookie。

    先读取明文 value；如果只有 encrypted_value，则尝试用 macOS 钥匙串中的
    Chromium Safe Storage 口令解密。
    """
    checked = 0
    encrypted_hits = 0
    for source in sources or default_chromium_sources():
        safe_storage_password: bytes | None = None
        safe_storage_loaded = False
        for cookie_db in _iter_cookie_databases(source.profile_root):
            checked += 1
            # 同一个浏览器 profile 只取一次解密材料，避免重复访问钥匙串或 Local State。
            if not safe_storage_loaded:
                safe_storage_password = _get_safe_storage_password(source.safe_storage_service)
                safe_storage_loaded = True
            cookies, encrypted_count = _read_cookies(
                cookie_db,
                domain=domain,
                safe_storage_password=safe_storage_password,
            )
            encrypted_hits += encrypted_count
            if cookies:
                cookie = "; ".join(f"{name}={value}" for name, value in cookies)
                profile_name = cookie_db.parent.name if cookie_db.parent.name != "Network" else cookie_db.parent.parent.name
                return BrowserCookieResult(
                    cookie=cookie,
                    source=f"{source.name}/{profile_name}",
                    message=f"已从 {source.name}/{profile_name} 读取 {len(cookies)} 个 Cookie",
                )
    if encrypted_hits:
        return BrowserCookieResult(
            cookie="",
            source="",
            message=_encrypted_cookie_failure_message(encrypted_hits),
        )
    if checked:
        return BrowserCookieResult(cookie="", source="", message="已检查浏览器 Cookie 数据库，但没有找到语雀 Cookie")
    return BrowserCookieResult(cookie="", source="", message="未找到支持的浏览器 Cookie 数据库")


def _iter_cookie_databases(profile_root: Path) -> list[Path]:
    """枚举 profile 下可能存在的 Chromium Cookie 数据库。"""
    if not profile_root.exists():
        return []
    candidates: list[Path] = []
    for profile_dir in sorted(profile_root.iterdir()):
        if not profile_dir.is_dir():
            continue
        for relative in (Path("Network") / "Cookies", Path("Cookies")):
            cookie_db = profile_dir / relative
            if cookie_db.exists() and cookie_db.is_file():
                candidates.append(cookie_db)
    return candidates


def _encrypted_cookie_failure_message(encrypted_hits: int) -> str:
    """生成浏览器 Cookie 解密失败提示。"""
    return f"找到 {encrypted_hits} 个语雀 Cookie，但无法解密。请确认允许访问浏览器钥匙串项，或先解锁钥匙串后重试"


def _copy_sqlite_database(source_db: Path, copied_db: Path) -> bool:
    """复制 SQLite 数据库及 WAL/SHM 辅助文件，降低浏览器占用导致的读取失败。"""
    copied_db.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            shutil.copy2(source_db, copied_db)
            for suffix in ("-wal", "-shm"):
                sidecar = Path(f"{source_db}{suffix}")
                if sidecar.exists():
                    shutil.copy2(sidecar, Path(f"{copied_db}{suffix}"))
            return True
        except OSError:
            if attempt == 2:
                return False
            time.sleep(0.08)
    return False


def _read_cookies(
    cookie_db: Path,
    *,
    domain: str,
    safe_storage_password: bytes | None,
) -> tuple[list[tuple[str, str]], int]:
    """从单个 Cookie 数据库中提取语雀相关 Cookie。"""
    with tempfile.TemporaryDirectory(prefix="yuque2markdown-cookies-", ignore_cleanup_errors=True) as tmp:
        copied_db = Path(tmp) / "Cookies"
        # 复制到临时目录后读取，避免浏览器占用锁导致 sqlite 打不开。
        # Chromium 使用 WAL 时，最新 Cookie 可能还在 -wal 文件里，因此辅助文件也要一起复制。
        if not _copy_sqlite_database(cookie_db, copied_db):
            return [], 0
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(copied_db)
            conn.execute("PRAGMA query_only = ON")
            normalized_domain = domain.lstrip(".")
            rows = conn.execute(
                """
                SELECT host_key, name, value, encrypted_value, expires_utc
                FROM cookies
                WHERE host_key = ? OR host_key LIKE ?
                ORDER BY host_key, path, name
                """,
                (normalized_domain, f"%.{normalized_domain}"),
            ).fetchall()
        except sqlite3.Error:
            return [], 0
        finally:
            if conn is not None:
                conn.close()

    now_chrome = int((time.time() + CHROME_EPOCH_OFFSET_SECONDS) * 1_000_000)
    cookies: list[tuple[str, str]] = []
    encrypted_count = 0
    seen_pairs: set[tuple[str, str]] = set()
    for host, name, value, encrypted_value, expires_utc in rows:
        if expires_utc and int(expires_utc) <= now_chrome:
            continue
        name = str(name or "").strip()
        value = str(value or "")
        if not name:
            continue
        if value:
            pair = (str(host or ""), name)
            if pair not in seen_pairs:
                cookies.append((name, value))
                seen_pairs.add(pair)
            continue
        if encrypted_value:
            encrypted_bytes = bytes(encrypted_value)
            # 明文 value 为空时再尝试解密，贴近浏览器原始存储逻辑。
            decrypted = _decrypt_macos_chromium_cookie(
                encrypted_bytes,
                host_key=str(host or ""),
                password=safe_storage_password,
            )
            if decrypted:
                pair = (str(host or ""), name)
                if pair not in seen_pairs:
                    cookies.append((name, decrypted))
                    seen_pairs.add(pair)
                continue
            encrypted_count += 1
    return cookies, encrypted_count


def _get_safe_storage_password(service_name: str) -> bytes | None:
    """从 macOS 钥匙串读取 Chromium Safe Storage 口令。"""

    try:
        proc = subprocess.run(
            ["security", "find-generic-password", "-w", "-s", service_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    password = proc.stdout.rstrip(b"\n")
    return password or None


def _decrypt_macos_chromium_cookie(encrypted_value: bytes, *, host_key: str, password: bytes | None) -> str:
    """解密 macOS Chromium Cookie。

    Chrome/Edge/Brave 在 macOS 上通常使用 AES-128-CBC，key 由 Safe Storage
    口令通过 PBKDF2-HMAC-SHA1 派生。这里复用系统 openssl，避免引入第三方依赖。
    """
    if not password or not encrypted_value.startswith((b"v10", b"v11")):
        return ""
    ciphertext = encrypted_value[3:]
    if not ciphertext:
        return ""
    key = hashlib.pbkdf2_hmac("sha1", password, b"saltysalt", 1003, 16)
    iv = b" " * 16
    try:
        proc = subprocess.run(
            ["openssl", "enc", "-d", "-aes-128-cbc", "-K", key.hex(), "-iv", iv.hex()],
            input=ciphertext,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return ""
    if proc.returncode != 0:
        return ""
    return _decode_decrypted_cookie(proc.stdout, host_key=host_key)


def _decode_decrypted_cookie(raw: bytes, *, host_key: str = "") -> str:
    """解码 Chromium 解密后的 Cookie 明文。"""
    if not raw:
        return ""
    if host_key:
        host_hash = hashlib.sha256(host_key.encode("utf-8")).digest()
        if raw.startswith(host_hash):
            raw = raw[len(host_hash):]
    return raw.rstrip(b"\x00").decode("utf-8", errors="ignore")
