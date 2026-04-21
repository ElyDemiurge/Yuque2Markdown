from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field


@dataclass(slots=True)
class InlineChoice:
    key: str
    label: str
    checked: bool = False


@dataclass(slots=True)
class MenuItem:
    key: str
    title: str
    value: str = ""
    item_type: str = "action"
    focusable: bool = True
    input_style: bool = False
    edit_value: str | None = None
    indent: int = 0
    inline_choices: list[InlineChoice] = field(default_factory=list)
    inline_selected_index: int = 0


DEFAULT_HELP_LINES = ["TODO: Windows 菜单渲染待实现"]
EDIT_HELP_LINES = ["TODO: Windows 菜单渲染待实现"]
TEXT_HELP_LINES = ["TODO: Windows 菜单渲染待实现"]
CONFIRM_HELP_LINES = ["TODO: Windows 菜单渲染待实现"]
SELECT_HELP_LINES = ["TODO: Windows 菜单渲染待实现"]
MESSAGE_HELP_LINES = ["TODO: Windows 菜单渲染待实现"]
MIN_SCREEN_WIDTH = 0
MIN_SCREEN_HEIGHT = 0


@dataclass(slots=True)
class MenuRefreshState:
    lines: list[str]
    done: bool = False
    refresh_interval: float = 0.18
    result: object | None = None
    error: Exception | None = None


def _char_display_width(char: str) -> int:
    return 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1


def _display_width(text: str) -> int:
    return sum(_char_display_width(char) for char in text)


def _truncate(text: str, width: int) -> str:
    if width <= 0 or _display_width(text) <= width:
        return text
    if width == 1:
        return "…"
    result: list[str] = []
    current = 0
    for char in text:
        char_width = _char_display_width(char)
        if current + char_width > width - 1:
            break
        result.append(char)
        current += char_width
    return "".join(result) + "…"


def _screen_too_small_message(height: int, width: int) -> list[str]:
    return [f"当前窗口过小：{width}x{height}"]


def _render_screen_too_small(_stdscr, *, title: str, height: int, width: int) -> None:
    raise NotImplementedError(f"TODO: Windows 菜单渲染待实现（{title} / {width}x{height}）")


def _is_screen_too_small(_height: int, _width: int) -> bool:
    return False


def _layout_frame(height: int, width: int, help_text: list[str], item_count: int, transient_lines: list[str] | None, status_lines: list[str]) -> tuple[int, int, int, int]:
    _ = (height, help_text, item_count, transient_lines, status_lines)
    return max(60, width - 2), 0, 0, 0


def _render_framed_header(_stdscr, *, title: str, help_text: list[str], width: int, content_width: int, top: int, left: int, height: int) -> int:
    _ = (_stdscr, title, help_text, width, content_width, top, left, height)
    raise NotImplementedError("TODO: Windows 菜单渲染待实现")


def _draw_text(_stdscr, _row: int, _col: int, _text: str, *, width: int | None = None, attrs: int = 0) -> None:
    _ = (_stdscr, _row, _col, _text, width, attrs)
    raise NotImplementedError("TODO: Windows 菜单渲染待实现")


def _first_focusable_index(items: list[MenuItem], preferred: int = 0) -> int:
    if not items:
        return 0
    preferred = max(0, min(preferred, len(items) - 1))
    if items[preferred].focusable:
        return preferred
    for index, item in enumerate(items):
        if item.focusable:
            return index
    return 0


def _move_focus(items: list[MenuItem], current: int, step: int) -> int:
    if not items:
        return 0
    candidate = current
    for _ in range(len(items)):
        candidate += step
        if candidate < 0 or candidate >= len(items):
            return current
        if items[candidate].focusable:
            return candidate
    return current


def run_menu(
    title: str,
    items: list[MenuItem],
    status: str = "",
    *,
    status_lines: list[str] | None = None,
    help_lines: list[str] | None = None,
    initial_index: int = 0,
    transient_lines: list[str] | None = None,
    refresh_state: MenuRefreshState | None = None,
) -> str | None:
    _ = (title, items, status, status_lines, help_lines, initial_index, transient_lines, refresh_state)
    raise NotImplementedError("TODO: Windows menu.run_menu 待实现")


def prompt_text(label: str, initial: str = "", help_lines: list[str] | None = None) -> str | None:
    _ = (label, initial, help_lines)
    raise NotImplementedError("TODO: Windows menu.prompt_text 待实现")


def run_confirmation(
    title: str,
    lines: list[str],
    help_lines: list[str] | None = None,
    confirm_label: str = "确认导出",
    cancel_label: str = "取消",
) -> bool:
    _ = (title, lines, help_lines, confirm_label, cancel_label)
    raise NotImplementedError("TODO: Windows menu.run_confirmation 待实现")


def run_select_list(
    title: str,
    lines: list[str],
    *,
    initial_index: int = 0,
    help_lines: list[str] | None = None,
    filter_text: str = "",
    empty_message: str = "暂无可选项",
    disabled_indexes: set[int] | None = None,
) -> tuple[int | None, str]:
    _ = (title, lines, initial_index, help_lines, filter_text, empty_message, disabled_indexes)
    raise NotImplementedError("TODO: Windows menu.run_select_list 待实现")


def show_message(title: str, lines: list[str], help_lines: list[str] | None = None) -> None:
    _ = (title, lines, help_lines)
    raise NotImplementedError("TODO: Windows menu.show_message 待实现")


def run_waiting_message(title: str, lines: list[str], worker) -> object:
    _ = (title, lines, worker)
    raise NotImplementedError("TODO: Windows menu.run_waiting_message 待实现")
