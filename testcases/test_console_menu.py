"""控制台菜单工具测试。"""
import sys
sys.path.insert(0, ".")

from core_modules.console.menu import (
    CONFIRM_HELP_LINES,
    DEFAULT_HELP_LINES,
    MESSAGE_HELP_LINES,
    MIN_SCREEN_HEIGHT,
    MIN_SCREEN_WIDTH,
    MenuItem,
    SELECT_HELP_LINES,
    _apply_text_edit_key,
    _configure_escape_delay,
    _coerce_printable_key,
    _cursor_display_offset,
    _display_width,
    _enable_keypad,
    _filter_cursor_x,
    _first_focusable_index,
    _is_escape_key,
    _is_enter_key,
    _is_screen_too_small,
    _move_focus,
    _screen_too_small_message,
    _start_filter_buffer,
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


def test_coerce_printable_key_converts_getch_ascii_int() -> None:
    assert _coerce_printable_key(ord("a")) == "a"
    assert _coerce_printable_key("/") == "/"
    assert _coerce_printable_key("中") == "中"


def test_coerce_printable_key_rejects_non_printable_keys() -> None:
    assert _coerce_printable_key(10) is None
    assert _coerce_printable_key("\n") is None
    assert _coerce_printable_key(260) is None
    assert _coerce_printable_key(261) is None


def test_escape_key_detects_esc_from_getch_and_get_wch() -> None:
    assert _is_escape_key(27) is True
    assert _is_escape_key("\x1b") is True
    assert _is_escape_key("q") is False


def test_enter_key_detects_getch_and_get_wch_forms() -> None:
    assert _is_enter_key(10) is True
    assert _is_enter_key(13) is True
    assert _is_enter_key("\n") is True
    assert _is_enter_key("\r") is True
    assert _is_enter_key("q") is False


def test_enable_keypad_turns_on_keypad_mode() -> None:
    class DummyScreen:
        def __init__(self) -> None:
            self.enabled = None

        def keypad(self, enabled) -> None:
            self.enabled = enabled

    screen = DummyScreen()
    _enable_keypad(screen)
    assert screen.enabled is True


def test_configure_escape_delay_sets_low_escdelay_once(monkeypatch) -> None:
    import core_modules.console.menu_unix as menu_unix

    calls: list[int] = []
    monkeypatch.setattr(menu_unix.curses, "set_escdelay", lambda value: calls.append(value))
    monkeypatch.setattr(menu_unix, "_ESCDELAY_CONFIGURED", False)

    _configure_escape_delay()
    _configure_escape_delay()

    assert calls == [25]


def test_start_filter_buffer_keeps_existing_filter_when_reentering() -> None:
    chars, cursor = _start_filter_buffer("安卓")
    assert chars == ["安", "卓"]
    assert cursor == 2


def test_start_filter_buffer_appends_seed_key() -> None:
    chars, cursor = _start_filter_buffer("安卓", "逆")
    assert chars == ["安", "卓", "逆"]
    assert cursor == 3


def test_cursor_display_offset_uses_display_width_for_chinese() -> None:
    assert _cursor_display_offset(["安", "卓", "a"], 2) == 4
    assert _cursor_display_offset(["安", "卓", "a"], 3) == 5


def test_filter_cursor_x_accounts_for_prompt_and_wide_chars() -> None:
    assert _filter_cursor_x(10, 40, ["你", "好"], 2) == 10 + _display_width("过滤: 你好")


def test_apply_text_edit_key_moves_cursor_across_mixed_width_text() -> None:
    chars, cursor, handled = _apply_text_edit_key(260, list("An 安卓"), 5)
    assert handled is True
    assert chars == list("An 安卓")
    assert cursor == 4

    chars, cursor, handled = _apply_text_edit_key(261, chars, cursor)
    assert handled is True
    assert cursor == 5


def test_apply_text_edit_key_deletes_at_cursor_position() -> None:
    chars = list("An 安卓")
    chars, cursor, handled = _apply_text_edit_key(260, chars, 5)
    assert handled is True
    chars, cursor, handled = _apply_text_edit_key("\x7f", chars, cursor)
    assert handled is True
    assert "".join(chars) == "An 卓"
    assert cursor == 3


def test_screen_too_small_detects_small_terminal() -> None:
    assert _is_screen_too_small(MIN_SCREEN_HEIGHT - 1, MIN_SCREEN_WIDTH) is True
    assert _is_screen_too_small(MIN_SCREEN_HEIGHT, MIN_SCREEN_WIDTH - 1) is True
    assert _is_screen_too_small(MIN_SCREEN_HEIGHT, MIN_SCREEN_WIDTH) is False


def test_screen_too_small_message_contains_current_and_min_size() -> None:
    lines = _screen_too_small_message(20, 80)

    assert "80x20" in lines[0]
    assert f"{MIN_SCREEN_WIDTH}x{MIN_SCREEN_HEIGHT}" in lines[1]
    assert "宽度还差" in lines[2]
    assert "高度还差" in lines[2]


def test_help_lines_use_esc_instead_of_q() -> None:
    assert "Esc 返回" in DEFAULT_HELP_LINES[0]
    assert "Esc 取消" in CONFIRM_HELP_LINES[0]
    assert "Esc 返回" in SELECT_HELP_LINES[0]
    assert MESSAGE_HELP_LINES == ["Esc 返回"]
