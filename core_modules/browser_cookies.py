"""从本机浏览器读取语雀 Cookie。"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
import tempfile
import time
from dataclasses import dataclass
import hashlib
import base64
import ctypes
import ctypes.wintypes
import json
import os
import platform
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


def default_chromium_sources(home: Path | None = None) -> list[BrowserCookieSource]:
    """返回 macOS 上常见 Chromium 系浏览器的 Cookie 目录。"""
    root = home or Path.home()
    if platform.system() == "Windows":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", root / "AppData" / "Local"))
        return [
            BrowserCookieSource("Chrome", local_app_data / "Google" / "Chrome" / "User Data", ""),
            BrowserCookieSource("Edge", local_app_data / "Microsoft" / "Edge" / "User Data", ""),
            BrowserCookieSource("Brave", local_app_data / "BraveSoftware" / "Brave-Browser" / "User Data", ""),
            BrowserCookieSource("Chromium", local_app_data / "Chromium" / "User Data", ""),
        ]
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

    会优先读取明文 value；如果只有 encrypted_value，则尝试用 macOS 钥匙串中的
    Chromium Safe Storage 口令解密。
    """
    checked = 0
    encrypted_hits = 0
    for source in sources or default_chromium_sources():
        safe_storage_password: bytes | None = None
        windows_key: bytes | None = None
        for cookie_db in _iter_cookie_databases(source.profile_root):
            checked += 1
            if platform.system() == "Windows":
                if windows_key is None:
                    windows_key = _get_windows_chromium_key(source.profile_root)
            elif safe_storage_password is None:
                safe_storage_password = _get_safe_storage_password(source.safe_storage_service)
            cookies, encrypted_count = _read_cookies(
                cookie_db,
                domain=domain,
                safe_storage_password=safe_storage_password,
                windows_key=windows_key,
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
            message=f"找到 {encrypted_hits} 个语雀 Cookie，但无法解密。请确认允许访问浏览器钥匙串项，或先解锁钥匙串后重试",
        )
    if checked:
        return BrowserCookieResult(cookie="", source="", message="已检查浏览器 Cookie 数据库，但没有找到语雀 Cookie")
    return BrowserCookieResult(cookie="", source="", message="未找到支持的浏览器 Cookie 数据库")


def _iter_cookie_databases(profile_root: Path) -> list[Path]:
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


def _read_cookies(
    cookie_db: Path,
    *,
    domain: str,
    safe_storage_password: bytes | None,
    windows_key: bytes | None,
) -> tuple[list[tuple[str, str]], int]:
    with tempfile.TemporaryDirectory() as tmp:
        copied_db = Path(tmp) / "Cookies"
        try:
            shutil.copy2(cookie_db, copied_db)
        except OSError:
            return [], 0
        try:
            with sqlite3.connect(copied_db) as conn:
                rows = conn.execute(
                    """
                    SELECT host_key, name, value, encrypted_value, expires_utc
                    FROM cookies
                    WHERE host_key LIKE ?
                    ORDER BY host_key, path, name
                    """,
                    (f"%{domain}",),
                ).fetchall()
        except sqlite3.Error:
            return [], 0

    now_chrome = int((time.time() + CHROME_EPOCH_OFFSET_SECONDS) * 1_000_000)
    cookies: list[tuple[str, str]] = []
    encrypted_count = 0
    seen_pairs: set[tuple[str, str]] = set()
    for _host, name, value, encrypted_value, expires_utc in rows:
        if expires_utc and int(expires_utc) <= now_chrome:
            continue
        name = str(name or "").strip()
        value = str(value or "")
        if not name:
            continue
        if value:
            pair = (str(_host or ""), name)
            if pair not in seen_pairs:
                cookies.append((name, value))
                seen_pairs.add(pair)
            continue
        if encrypted_value:
            encrypted_bytes = bytes(encrypted_value)
            if platform.system() == "Windows":
                decrypted = _decrypt_windows_chromium_cookie(encrypted_bytes, windows_key=windows_key)
            else:
                decrypted = _decrypt_macos_chromium_cookie(encrypted_bytes, host_key=str(_host or ""), password=safe_storage_password)
            if decrypted:
                pair = (str(_host or ""), name)
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
    raw = proc.stdout
    host_hash = hashlib.sha256(host_key.encode("utf-8")).digest()
    if raw.startswith(host_hash):
        raw = raw[len(host_hash):]
    return raw.decode("utf-8", errors="ignore")


def _get_windows_chromium_key(profile_root: Path) -> bytes | None:
    local_state = profile_root / "Local State"
    if not local_state.exists():
        return None
    try:
        data = json.loads(local_state.read_text(encoding="utf-8"))
        encrypted_key = data.get("os_crypt", {}).get("encrypted_key")
        if not encrypted_key:
            return None
        raw_key = base64.b64decode(encrypted_key)
    except (OSError, ValueError, TypeError):
        return None
    if raw_key.startswith(b"DPAPI"):
        raw_key = raw_key[5:]
    return _windows_crypt_unprotect_data(raw_key)


def _decrypt_windows_chromium_cookie(encrypted_value: bytes, *, windows_key: bytes | None) -> str:
    if encrypted_value.startswith((b"v10", b"v11")):
        if not windows_key or len(encrypted_value) < 3 + 12 + 16:
            return ""
        nonce = encrypted_value[3:15]
        ciphertext = encrypted_value[15:-16]
        tag = encrypted_value[-16:]
        raw = _windows_aes_gcm_decrypt(windows_key, nonce, ciphertext, tag)
        return raw.decode("utf-8", errors="ignore") if raw else ""
    raw = _windows_crypt_unprotect_data(encrypted_value)
    return raw.decode("utf-8", errors="ignore") if raw else ""


def _windows_crypt_unprotect_data(data: bytes) -> bytes | None:
    if platform.system() != "Windows":
        return None

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    in_buffer = ctypes.create_string_buffer(data)
    in_blob = DATA_BLOB(len(data), ctypes.cast(in_buffer, ctypes.POINTER(ctypes.c_char)))
    out_blob = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)):
        return None
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        kernel32.LocalFree(out_blob.pbData)


def _windows_aes_gcm_decrypt(key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes) -> bytes | None:
    if platform.system() != "Windows":
        return None
    bcrypt = ctypes.windll.bcrypt
    BCRYPT_AES_ALGORITHM = "AES"
    BCRYPT_CHAIN_MODE_GCM = "ChainingModeGCM"
    BCRYPT_CHAINING_MODE = "ChainingMode"
    STATUS_SUCCESS = 0

    alg = ctypes.c_void_p()
    key_handle = ctypes.c_void_p()
    result = bcrypt.BCryptOpenAlgorithmProvider(ctypes.byref(alg), BCRYPT_AES_ALGORITHM, None, 0)
    if result != STATUS_SUCCESS:
        return None
    try:
        mode = ctypes.create_unicode_buffer(BCRYPT_CHAIN_MODE_GCM)
        result = bcrypt.BCryptSetProperty(
            alg,
            BCRYPT_CHAINING_MODE,
            ctypes.cast(mode, ctypes.POINTER(ctypes.c_ubyte)),
            ctypes.sizeof(mode),
            0,
        )
        if result != STATUS_SUCCESS:
            return None
        key_buffer = ctypes.create_string_buffer(key)
        result = bcrypt.BCryptGenerateSymmetricKey(
            alg,
            ctypes.byref(key_handle),
            None,
            0,
            ctypes.cast(key_buffer, ctypes.POINTER(ctypes.c_ubyte)),
            len(key),
            0,
        )
        if result != STATUS_SUCCESS:
            return None

        class BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.wintypes.ULONG),
                ("dwInfoVersion", ctypes.wintypes.ULONG),
                ("pbNonce", ctypes.POINTER(ctypes.c_ubyte)),
                ("cbNonce", ctypes.wintypes.ULONG),
                ("pbAuthData", ctypes.POINTER(ctypes.c_ubyte)),
                ("cbAuthData", ctypes.wintypes.ULONG),
                ("pbTag", ctypes.POINTER(ctypes.c_ubyte)),
                ("cbTag", ctypes.wintypes.ULONG),
                ("pbMacContext", ctypes.POINTER(ctypes.c_ubyte)),
                ("cbMacContext", ctypes.wintypes.ULONG),
                ("cbAAD", ctypes.wintypes.ULONG),
                ("cbData", ctypes.c_ulonglong),
                ("dwFlags", ctypes.wintypes.ULONG),
            ]

        nonce_buffer = ctypes.create_string_buffer(nonce)
        tag_buffer = ctypes.create_string_buffer(tag)
        auth_info = BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO()
        auth_info.cbSize = ctypes.sizeof(BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO)
        auth_info.dwInfoVersion = 1
        auth_info.pbNonce = ctypes.cast(nonce_buffer, ctypes.POINTER(ctypes.c_ubyte))
        auth_info.cbNonce = len(nonce)
        auth_info.pbTag = ctypes.cast(tag_buffer, ctypes.POINTER(ctypes.c_ubyte))
        auth_info.cbTag = len(tag)

        cipher_buffer = ctypes.create_string_buffer(ciphertext)
        plain_buffer = ctypes.create_string_buffer(len(ciphertext))
        plain_len = ctypes.wintypes.ULONG()
        result = bcrypt.BCryptDecrypt(
            key_handle,
            ctypes.cast(cipher_buffer, ctypes.POINTER(ctypes.c_ubyte)),
            len(ciphertext),
            ctypes.byref(auth_info),
            None,
            0,
            ctypes.cast(plain_buffer, ctypes.POINTER(ctypes.c_ubyte)),
            len(ciphertext),
            ctypes.byref(plain_len),
            0,
        )
        if result != STATUS_SUCCESS:
            return None
        return plain_buffer.raw[:plain_len.value]
    finally:
        if key_handle:
            bcrypt.BCryptDestroyKey(key_handle)
        bcrypt.BCryptCloseAlgorithmProvider(alg, 0)
