"""控制台菜单工具测试。"""
import importlib
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
    _is_backspace_key,
    _is_delete_key,
    _is_down_key,
    _is_escape_key,
    _is_enter_key,
    _is_interrupt_key,
    _is_left_key,
    _is_right_key,
    _is_screen_too_small,
    _is_up_key,
    _move_focus,
    _normalize_terminal_text,
    _pad_to_width,
    _read_key,
    _render_inline_choice_menu_item,
    _screen_too_small_message,
    _set_cursor,
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


def test_windows_key_helpers_accept_common_key_codes() -> None:
    assert _is_backspace_key(8) is True
    assert _is_backspace_key(127) is True
    assert _is_delete_key(330) is True
    assert _is_up_key(259) is True
    assert _is_down_key(258) is True
    assert _is_left_key(260) is True
    assert _is_right_key(261) is True


def test_interrupt_key_detects_ctrl_c() -> None:
    assert _is_interrupt_key(3) is True
    assert _is_interrupt_key("\x03") is True
    assert _is_interrupt_key(13) is False


def test_enable_keypad_turns_on_keypad_mode() -> None:
    class DummyScreen:
        def __init__(self) -> None:
            self.enabled = None

        def keypad(self, enabled) -> None:
            self.enabled = enabled

    screen = DummyScreen()
    _enable_keypad(screen)
    assert screen.enabled is True


def test_set_cursor_ignores_curses_errors(monkeypatch) -> None:
    menu_backend = importlib.import_module(_set_cursor.__module__)

    def boom(_visibility):
        raise menu_backend.curses.error("unsupported")

    monkeypatch.setattr(menu_backend.curses, "curs_set", boom)

    _set_cursor(1)


def test_read_key_falls_back_to_minus_one_on_wide_read_error() -> None:
    menu_backend = importlib.import_module(_read_key.__module__)

    class DummyScreen:
        def get_wch(self):
            raise menu_backend.curses.error("boom")

        def getch(self):
            return ord("x")

    assert _read_key(DummyScreen(), wide=True) == -1
    assert _read_key(DummyScreen(), wide=False) == ord("x")


def test_configure_escape_delay_sets_low_escdelay_once(monkeypatch) -> None:
    menu_backend = importlib.import_module(_configure_escape_delay.__module__)

    calls: list[int] = []
    monkeypatch.setattr(menu_backend.curses, "set_escdelay", lambda value: calls.append(value), raising=False)
    monkeypatch.setattr(menu_backend, "_ESCDELAY_CONFIGURED", False)

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


def test_windows_help_lines_avoid_ambiguous_width_glyphs() -> None:
    joined = "\n".join(DEFAULT_HELP_LINES + SELECT_HELP_LINES + CONFIRM_HELP_LINES)
    assert not set("↑↓←→").intersection(joined)


def test_pad_to_width_accounts_for_wide_characters() -> None:
    padded = _pad_to_width("中a", 5)
    assert _display_width(padded) == 5
    assert padded.endswith("  ")


def test_pad_to_width_normalizes_unstable_glyphs() -> None:
    assert _pad_to_width("─›", 4) == "->  "


def test_windows_terminal_text_replaces_unstable_glyphs() -> None:
    normalized = _normalize_terminal_text("↑↓ 移动 | ←→ 展开 | ── 连接 ── | 更多 › | 省略…")

    assert normalized == "Up/Down 移动 | Left/Right 展开 | -- 连接 -- | 更多 > | 省略..."
    assert not set("─·›↑↓←→…").intersection(normalized)


def test_draw_text_normalizes_and_pads_to_requested_width() -> None:
    class DummyScreen:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int, str, int]] = []

        def getmaxyx(self) -> tuple[int, int]:
            return 10, 40

        def addstr(self, row: int, col: int, text: str, attrs: int) -> None:
            self.calls.append((row, col, text, attrs))

    menu_backend = importlib.import_module(_normalize_terminal_text.__module__)
    screen = DummyScreen()

    menu_backend._draw_text(screen, 1, 2, "↑↓ ── › …", width=20)

    assert screen.calls == [(1, 2, "Up/Down -- > ...    ", 0)]
    assert menu_backend._display_width(screen.calls[0][2]) == 20


def test_inline_choice_render_keeps_browser_cookie_label_complete() -> None:
    class DummyScreen:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int, str, int]] = []

        def getmaxyx(self) -> tuple[int, int]:
            return 10, 80

        def addstr(self, row: int, col: int, text: str, attrs: int) -> None:
            self.calls.append((row, col, text, attrs))

    from core_modules.console.menu import InlineChoice

    screen = DummyScreen()
    item = MenuItem(
        "auth_mode",
        "登录方式: ",
        inline_choices=[
            InlineChoice("cookie", "浏览器 Cookie"),
            InlineChoice("token", "Token", checked=True),
        ],
        inline_selected_index=1,
    )

    _render_inline_choice_menu_item(
        screen,
        item=item,
        row=1,
        left=0,
        content_width=50,
        prefix=">",
        title_indent="",
        attrs=0,
        selected=True,
    )

    rendered = "".join(call[2] for call in screen.calls)
    assert "[ ] 浏览器 Cookie" in rendered
    assert "[*] Token" in rendered
