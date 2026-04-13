from __future__ import annotations

import json
import sys
import warnings
from dataclasses import asdict
from pathlib import Path

from core_modules.config.models import AppConfig, ExportDefaultsConfig, ProxyConfig, UiPreferences

from core_modules.config.validator import validate_config, format_validation_errors, ValidationError

CONFIG_FILE_NAME = "yuque2markdown.config.json"


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
    proxy = ProxyConfig(**proxy_data) if proxy_data else ProxyConfig()
    config = AppConfig(
        version=int(data.get("version", 1)),
        token=str(data.get("token", "")),
        persist_token=bool(data.get("persist_token", True)),
        last_repo_input=str(data.get("last_repo_input", "")),
        export_defaults=ExportDefaultsConfig(**export_defaults, proxy=proxy),
        ui_preferences=UiPreferences(**ui_preferences),
    )

    # Validate loaded config and warn about issues
    errors = validate_config(config)
    if errors:
        error_lines = format_validation_errors(errors)
        sys.stderr.write("\n".join(error_lines) + "\n")
        for err in errors:
            warnings.warn(f"配置字段 {err.field}: {err.message}")

    return config


def validate_config_on_save(config: AppConfig) -> list[ValidationError]:
    """Validate configuration before saving. Returns validation errors if any."""
    return validate_config(config)


def save_config(config: AppConfig, base_dir: Path | None = None, *, validate: bool = True) -> Path:
    if validate:
        errors = validate_config(config)
        if errors:
            error_lines = format_validation_errors(errors)
            raise ValueError("\n".join(error_lines))

    path = config_path(base_dir)
    payload = asdict(config)
    if not config.persist_token:
        payload["token"] = ""
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
