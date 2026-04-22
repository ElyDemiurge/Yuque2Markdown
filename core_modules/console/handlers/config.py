"""控制台配置持久化辅助函数。

本模块负责把会话状态折叠回配置对象，并在需要时写入磁盘。
"""

from __future__ import annotations

from dataclasses import replace

from core_modules.config.models import AppConfig, SessionState
from core_modules.config.store import save_config


def apply_session_to_config(config: AppConfig, session: SessionState) -> AppConfig:
    """将当前会话中的关键选择同步到配置对象。

    参数:
        config: 当前应用配置。
        session: 当前控制台会话状态。

    返回:
        基于 ``config`` 复制出的新配置对象，避免直接原地修改调用方持有的实例。
    """
    updated = replace(config)
    updated.last_repo_input = session.repo_input or config.last_repo_input
    if not updated.persist_token:
        updated.token = ""
    return updated


def persist_config(config: AppConfig, session: SessionState, reason: str, *, append_console_log) -> AppConfig:
    """保存配置并同步更新会话状态。

    参数:
        config: 当前应用配置。
        session: 当前控制台会话状态。
        reason: 本次保存的触发原因，用于日志与瞬时提示。
        append_console_log: 控制台日志追加函数。

    返回:
        写盘后的配置对象。
    """
    updated = apply_session_to_config(config, session)
    path = save_config(updated)
    session.dirty = False
    session.status_message = "配置已保存"
    session.transient_lines = [f"已保存配置 ({reason})"]
    append_console_log(f"保存配置: 原因={reason} 文件={path.name}")
    return updated
