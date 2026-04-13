"""Configuration helpers for Yuque2Markdown console."""

from __future__ import annotations

from dataclasses import replace

from core_modules.config.models import AppConfig, SessionState
from core_modules.config.store import save_config


def apply_session_to_config(config: AppConfig, session: SessionState) -> AppConfig:
    """Apply session values to persistent config."""
    updated = replace(config)
    updated.last_repo_input = session.repo_input or config.last_repo_input
    if not updated.persist_token:
        updated.token = ""
    return updated


def persist_config(config: AppConfig, session: SessionState, reason: str, *, append_console_log) -> AppConfig:
    """Persist config and update session flags."""
    updated = apply_session_to_config(config, session)
    path = save_config(updated)
    session.dirty = False
    session.status_message = "配置已保存"
    session.transient_lines = [f"已保存配置 ({reason})"]
    append_console_log(f"CONFIG_SAVE reason={reason} path={path.name}")
    return updated
