from __future__ import annotations

import json
import sys
import warnings
from dataclasses import asdict
from pathlib import Path

from core_modules.config.models import (
    AppConfig,
    AUTH_MODE_TOKEN,
    DEFAULT_ATTACHMENT_SUFFIXES,
    ExportDefaultsConfig,
    ProxyConfig,
    UiPreferences,
    normalize_auth_mode,
    normalize_attachment_suffixes,
)

from core_modules.config.validator import validate_config, format_validation_errors

CONFIG_FILE_NAME = "yuque2markdown.config.json"


def _translate_legacy_file_type(file_type: object) -> list[str]:
    mapping = {
        0: list(DEFAULT_ATTACHMENT_SUFFIXES),
        1: [],
        2: [],
        3: [".pdf"],
        4: [".pdf"],
    }
    try:
        return mapping.get(int(file_type), list(DEFAULT_ATTACHMENT_SUFFIXES))
    except (TypeError, ValueError):
        return list(DEFAULT_ATTACHMENT_SUFFIXES)


def config_path(base_dir: Path | None = None) -> Path:
    root = base_dir or Path.cwd()
    return root / CONFIG_FILE_NAME


def load_config(base_dir: Path | None = None) -> AppConfig:
    path = config_path(base_dir)
    if not path.exists():
        return AppConfig()
    data = json.loads(path.read_text(encoding="utf-8"))
    export_defaults = data.get("export_defaults", {})
    ui_preferences = data.get("ui_preferences", {})
    proxy_data = export_defaults.pop("proxy", {})
    legacy_file_type = export_defaults.pop("file_type", None)
    attachment_suffixes = export_defaults.get("attachment_suffixes")
    if attachment_suffixes is None and legacy_file_type is not None:
        export_defaults["attachment_suffixes"] = _translate_legacy_file_type(legacy_file_type)
    else:
        export_defaults["attachment_suffixes"] = normalize_attachment_suffixes(attachment_suffixes)
    proxy = ProxyConfig(**proxy_data) if proxy_data else ProxyConfig()
    config = AppConfig(
        version=int(data.get("version", 1)),
        auth_mode=normalize_auth_mode(str(data.get("auth_mode", AUTH_MODE_TOKEN))),
        token=str(data.get("token", "")),
        cookie=str(data.get("cookie", "")),
        persist_token=bool(data.get("persist_token", True)),
        persist_cookie=bool(data.get("persist_cookie", True)),
        last_repo_input=str(data.get("last_repo_input", "")),
        export_defaults=ExportDefaultsConfig(**export_defaults, proxy=proxy),
        ui_preferences=UiPreferences(**ui_preferences),
    )

    # 配置读入后先做一次校验，便于尽早发现旧字段或非法值。
    errors = validate_config(config)
    if errors:
        error_lines = format_validation_errors(errors)
        sys.stderr.write("\n".join(error_lines) + "\n")
        for err in errors:
            warnings.warn(f"配置字段 {err.field}: {err.message}")

    return config

def save_config(config: AppConfig, base_dir: Path | None = None, *, validate: bool = True) -> Path:
    if validate:
        errors = validate_config(config)
        if errors:
            error_lines = format_validation_errors(errors)
            raise ValueError("\n".join(error_lines))

    path = config_path(base_dir)
    payload = asdict(config)
    payload["export_defaults"]["attachment_suffixes"] = normalize_attachment_suffixes(
        config.export_defaults.attachment_suffixes
    )
    if not config.persist_token:
        payload["token"] = ""
    if not config.persist_cookie:
        payload["cookie"] = ""
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
