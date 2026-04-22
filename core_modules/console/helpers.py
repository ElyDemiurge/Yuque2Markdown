"""Yuque2Markdown 控制台通用辅助函数。

本模块只放置与界面无关的纯函数，便于单元测试复用。
"""

from __future__ import annotations

from core_modules.config.models import AppConfig


def parse_action(action: str | None) -> tuple[str, str | None]:
    """解析菜单动作字符串。

    参数:
        action: 菜单返回的动作字符串，普通动作通常是 ``"save"``，
            编辑动作通常是 ``"token:xxxx"``。

    返回:
        一个二元组 ``(动作键, 编辑值)``。当 ``action`` 为空时，返回 ``("", None)``。

    说明:
        该函数不抛出异常，调用方可直接按返回值分支处理。
    """
    if action is None:
        return "", None
    if ":" in action:
        key, value = action.split(":", 1)
        return key, value
    return action, None


def parse_non_negative_float(value: str | None) -> float | None:
    """将字符串解析为非负浮点数。

    参数:
        value: 用户输入的文本，可为空。

    返回:
        解析成功时返回非负浮点数；输入为空、格式错误或小于 0 时返回 ``None``。
    """
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
    """将字符串解析为正整数。

    参数:
        value: 用户输入的文本，可为空。

    返回:
        解析成功时返回大于 0 的整数；输入为空、格式错误或小于 1 时返回 ``None``。
    """
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
    """解析可选正整数，空白输入视为未设置。

    参数:
        value: 用户输入的文本，可为空或只包含空白字符。

    返回:
        空字符串或空白字符串返回 ``None``；其余情况复用 :func:`parse_positive_int`
        的校验逻辑。
    """
    if value is None:
        return None
    if not value.strip():
        return None
    return parse_positive_int(value)


def toggle_config_value(config: AppConfig, action: str) -> None:
    """根据动作键切换控制台中的布尔配置项。

    参数:
        config: 当前应用配置对象。
        action: 菜单动作键。

    说明:
        未识别的动作键会被静默忽略，以保持菜单层调用逻辑简洁。
    """
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
    """按关键字过滤知识库列表。

    参数:
        repos: 语雀接口返回的知识库列表。
        filter_text: 用户输入的过滤关键字。

    返回:
        命中名称、命名空间或 slug 的知识库列表。若过滤词为空，则直接返回原列表。
    """
    if not filter_text:
        return repos
    query = filter_text.lower()
    result: list[dict] = []
    for repo in repos:
        # 统一拼接常见检索字段，便于实现稳定的大小写无关匹配。
        parts = [str(repo.get("name") or ""), str(repo.get("namespace") or ""), str(repo.get("slug") or "")]
        haystack = " ".join(parts).lower()
        if query in haystack:
            result.append(repo)
    return result
