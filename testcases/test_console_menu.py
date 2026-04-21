"""控制台菜单工具测试。"""
import sys
sys.path.insert(0, ".")

from core_modules.console.menu import (
    MIN_SCREEN_HEIGHT,
    MIN_SCREEN_WIDTH,
    MenuItem,
    _display_width,
    _first_focusable_index,
    _is_screen_too_small,
    _move_focus,
    _screen_too_small_message,
    _truncate,
)


def test_first_focusable_index_skips_readonly_and_section() -> None:
    items = [
        MenuItem("section", "连接", item_type="section", focusable=False),
        MenuItem("status", "状态", item_type="readonly", focusable=False),
        MenuItem("token", "设置 Token"),
    ]

    assert _first_focusable_index(items, preferred=0) == 2


def test_move_focus_skips_non_focusable_items() -> None:
    items = [
        MenuItem("section", "连接", item_type="section", focusable=False),
        MenuItem("token", "设置 Token"),
        MenuItem("status", "状态", item_type="readonly", focusable=False),
        MenuItem("save", "保存配置"),
    ]

    assert _move_focus(items, 1, 1) == 3
    assert _move_focus(items, 3, -1) == 1


def test_truncate_respects_display_width_for_chinese_text() -> None:
    text = "登录方式: [ ] 浏览器 Cookie   [*] Token"

    truncated = _truncate(text, 16)

    assert _display_width(truncated) <= 16
    assert truncated.endswith("...")


def test_truncate_keeps_short_chinese_text() -> None:
    assert _truncate("设置 Token", 16) == "设置 Token"


def test_screen_too_small_detects_small_terminal() -> None:
    assert _is_screen_too_small(MIN_SCREEN_HEIGHT - 1, MIN_SCREEN_WIDTH) is True
    assert _is_screen_too_small(MIN_SCREEN_HEIGHT, MIN_SCREEN_WIDTH - 1) is True
    assert _is_screen_too_small(MIN_SCREEN_HEIGHT, MIN_SCREEN_WIDTH) is False


def test_screen_too_small_message_contains_current_and_min_size() -> None:
    lines = _screen_too_small_message(20, 80)

    assert "80x20" in lines[0]
    assert f"{MIN_SCREEN_WIDTH}x{MIN_SCREEN_HEIGHT}" in lines[1]
