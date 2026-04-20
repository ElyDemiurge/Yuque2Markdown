"""Yuque2Markdown 控制台通用辅助函数。"""

from __future__ import annotations

from core_modules.config.models import AppConfig


def parse_action(action: str | None) -> tuple[str, str | None]:
    """解析菜单动作字符串，返回动作键和编辑值。"""
    if action is None:
        return "", None
    if ":" in action:
        key, value = action.split(":", 1)
        return key, value
    return action, None


def parse_non_negative_float(value: str | None) -> float | None:
    """解析非负浮点数输入。"""
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    if parsed < 0:
        return None
    return parsed


def parse_positive_int(value: str | None) -> int | None:
    """解析正整数输入。"""
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    if parsed < 1:
        return None
    return parsed


def parse_optional_positive_int(value: str | None) -> int | None:
    """解析可选正整数输入，空字符串视为未设置。"""
    if value is None:
        return None
    if not value.strip():
        return None
    return parse_positive_int(value)


def toggle_config_value(config: AppConfig, action: str) -> None:
    """切换控制台里的布尔配置项。"""
    if action == "resume":
        config.export_defaults.resume = not config.export_defaults.resume
    elif action == "strict":
        config.export_defaults.strict = not config.export_defaults.strict
    elif action == "offline_assets":
        config.export_defaults.offline_assets = not config.export_defaults.offline_assets
    elif action == "fail_on_asset_error":
        config.export_defaults.fail_on_asset_error = not config.export_defaults.fail_on_asset_error
    elif action == "confirm_before_export":
        config.ui_preferences.confirm_before_export = not config.ui_preferences.confirm_before_export
    elif action == "auto_save_after_export":
        config.ui_preferences.auto_save_after_export = not config.ui_preferences.auto_save_after_export
    elif action == "persist_token":
        config.persist_token = not config.persist_token
    elif action == "persist_cookie":
        config.persist_cookie = not config.persist_cookie


def filter_repos(repos: list[dict], filter_text: str) -> list[dict]:
    """按关键字过滤知识库列表。"""
    if not filter_text:
        return repos
    query = filter_text.lower()
    result: list[dict] = []
    for repo in repos:
        parts = [str(repo.get("name") or ""), str(repo.get("namespace") or ""), str(repo.get("slug") or "")]
        haystack = " ".join(parts).lower()
        if query in haystack:
            result.append(repo)
    return result
