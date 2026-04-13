from __future__ import annotations

import curses
import threading
import time
import unicodedata
from dataclasses import dataclass


@dataclass(slots=True)
class MenuItem:
    """定义控制台菜单项的显示与交互属性。"""
    key: str
    title: str
    value: str = ""
    item_type: str = "action"
    focusable: bool = True
    input_style: bool = False
    edit_value: str | None = None  # 编辑时的初始值，None 时使用 value
    indent: int = 0  # 缩进级别，每个级别 4 个空格


DEFAULT_HELP_LINES = ["↑↓ 移动 | Enter 确认/编辑 | Space 切换 | s 手动保存配置 | q 返回"]
EDIT_HELP_LINES = ["Enter 确认 | Esc 取消 | ↑↓ 放弃编辑 | ←→ 移动 | Backspace/Delete 删除"]
TEXT_HELP_LINES = ["输入内容后 Enter 确认 | Esc 取消 | ←→ 移动 | Backspace/Delete 删除"]
CONFIRM_HELP_LINES = ["↑↓ 移动 | Enter 确认 | q 取消"]
SELECT_HELP_LINES = ["↑↓ 移动 | Enter 选择 | q 返回 | 输入开始过滤 | / 过滤模式 | Backspace 清空"]
MESSAGE_HELP_LINES = ["任意键返回"]
WAITING_FRAMES = [".", "..", "...", "....", ".....", "......"]


@dataclass(slots=True)
class MenuRefreshState:
    """保存菜单异步刷新时的临时状态。"""
    lines: list[str]
    done: bool = False
    refresh_interval: float = 0.18
    result: object | None = None
    error: Exception | None = None


def _layout_frame(height: int, width: int, help_text: list[str], item_count: int, transient_lines: list[str] | None, status_lines: list[str]) -> tuple[int, int, int, int]:
    content_width = min(width - 1, max(60, min(128, width - 4)))
    left = max(0, (width - content_width) // 2)
    transient_height = len(transient_lines) + 1 if transient_lines else 0
    header_height = 1 + len(help_text) + 1
    body_height = item_count
    top_margin = max(1, height // 8)
    top = min(max(0, top_margin), max(0, height - (header_height + transient_height + body_height + 2)))
    divider_row = top + len(help_text) + 1
    return content_width, left, top, divider_row


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
    """渲染通用菜单并返回用户选择的动作。"""
    lines = status_lines if status_lines is not None else ([status] if status else [])
    index = _first_focusable_index(items, preferred=initial_index)
    editing_index: int | None = None
    edit_chars: list[str] = []
    edit_cursor: int = 0

    def _render(stdscr) -> str | None:
        nonlocal index, transient_lines, editing_index, edit_chars, edit_cursor
        curses.curs_set(0)
        if refresh_state is not None:
            stdscr.timeout(max(1, int(refresh_state.refresh_interval * 1000)))
        else:
            stdscr.timeout(-1)
        while True:
            stdscr.clear()
            if refresh_state is not None:
                transient_lines = refresh_state.lines
            height, width = stdscr.getmaxyx()
            if editing_index is not None:
                help_text = help_lines or EDIT_HELP_LINES
            else:
                help_text = help_lines or DEFAULT_HELP_LINES
            content_width, left, top, divider_row = _layout_frame(height, width, help_text, len(items), transient_lines, lines)
            stdscr.addnstr(top, max(0, (width - min(_display_width(title), content_width)) // 2), title, min(content_width, width), curses.A_BOLD)
            for offset, line in enumerate(help_text, start=1):
                row = top + offset
                if row >= height:
                    break
                centered_line = _truncate(line, content_width)
                line_x = max(0, (width - _display_width(centered_line)) // 2)
                stdscr.addnstr(row, line_x, centered_line, min(content_width, width - line_x), curses.A_BOLD)
            if divider_row < height:
                stdscr.addnstr(divider_row, left, "─" * max(0, content_width), content_width)
            row = divider_row + 1
            if transient_lines:
                for line in transient_lines:
                    if row >= height:
                        break
                    stdscr.addnstr(row, left + 2, _truncate(line, max(0, content_width - 2)), max(0, content_width - 2), curses.A_DIM)
                    row += 1
                if row < height:
                    row += 1
            edit_cursor_pos, menu_end_row = _render_menu_items(stdscr, items, index, row, left, content_width, height, editing_index, edit_chars, edit_cursor)
            _render_status_lines(stdscr, lines, menu_end_row, left, content_width, height)
            if editing_index is not None:
                curses.curs_set(2)  # 块状光标更明显
                stdscr.move(edit_cursor_pos[0], edit_cursor_pos[1])
                key = stdscr.get_wch()
            else:
                curses.curs_set(0)  # 非编辑时隐藏光标
                key = stdscr.getch()
            if key == -1:
                if refresh_state is not None and refresh_state.done:
                    transient_lines = []
                    return "__refresh_done__"
                continue
            if editing_index is not None:
                if key in ("\n", "\r"):
                    result = "".join(edit_chars).strip()
                    item_key = items[editing_index].key
                    editing_index = None
                    edit_chars = []
                    edit_cursor = 0
                    curses.curs_set(0)
                    return f"{item_key}:{result}"
                if key == "\x1b":
                    editing_index = None
                    edit_chars = []
                    edit_cursor = 0
                    curses.curs_set(0)
                    continue
                if key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
                    if edit_cursor > 0:
                        del edit_chars[edit_cursor - 1]
                        edit_cursor -= 1
                    continue
                if key == curses.KEY_DC:
                    if edit_cursor < len(edit_chars):
                        del edit_chars[edit_cursor]
                    continue
                if key == curses.KEY_LEFT:
                    edit_cursor = max(0, edit_cursor - 1)
                    continue
                if key == curses.KEY_RIGHT:
                    edit_cursor = min(len(edit_chars), edit_cursor + 1)
                    continue
                if key == curses.KEY_UP:
                    editing_index = None
                    edit_chars = []
                    edit_cursor = 0
                    curses.curs_set(0)
                    index = _move_focus(items, index, -1)
                    continue
                if key == curses.KEY_DOWN:
                    editing_index = None
                    edit_chars = []
                    edit_cursor = 0
                    curses.curs_set(0)
                    index = _move_focus(items, index, 1)
                    continue
                if isinstance(key, str) and key.isprintable():
                    edit_chars.insert(edit_cursor, key)
                    edit_cursor += 1
                continue
            if key == curses.KEY_UP:
                index = _move_focus(items, index, -1)
            elif key == curses.KEY_DOWN:
                index = _move_focus(items, index, 1)
            elif key in (10, 13):
                if 0 <= index < len(items) and items[index].focusable:
                    item = items[index]
                    if item.input_style:
                        editing_index = index
                        initial = item.edit_value if item.edit_value is not None else item.value
                        edit_chars = list(initial)
                        edit_cursor = len(edit_chars)
                        curses.curs_set(1)
                        continue
                    return item.key
            elif key == ord("q"):
                return None
            elif key == ord("s"):
                return "save"
            elif key == ord(" ") and 0 <= index < len(items) and items[index].item_type == "bool":
                return items[index].key

    return curses.wrapper(_render)


def prompt_text(label: str, initial: str = "", help_lines: list[str] | None = None) -> str | None:
    """读取一段文本输入并返回用户确认后的内容。"""
    chars = list(initial)
    cursor = len(chars)

    def _run(stdscr) -> str | None:
        nonlocal chars, cursor
        curses.curs_set(1)
        while True:
            stdscr.clear()
            _, width = stdscr.getmaxyx()
            stdscr.addnstr(0, 0, label, width - 1, curses.A_BOLD)
            for row, line in enumerate(help_lines or TEXT_HELP_LINES, start=1):
                stdscr.addnstr(row, 0, _truncate(line, width - 1), width - 1, curses.A_BOLD)
            text = "".join(chars)
            stdscr.addnstr(3, 0, text, width - 1)
            stdscr.move(3, min(cursor, max(0, width - 2)))
            key = stdscr.get_wch()
            if key in ("\n", "\r"):
                return text.strip()
            if key == "\x1b":
                return None
            if key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
                if cursor > 0:
                    del chars[cursor - 1]
                    cursor -= 1
                continue
            if key == curses.KEY_DC:
                if cursor < len(chars):
                    del chars[cursor]
                continue
            if key == curses.KEY_LEFT:
                cursor = max(0, cursor - 1)
                continue
            if key == curses.KEY_RIGHT:
                cursor = min(len(chars), cursor + 1)
                continue
            if isinstance(key, str) and key.isprintable():
                chars.insert(cursor, key)
                cursor += 1

    return curses.wrapper(_run)


def run_confirmation(
    title: str,
    lines: list[str],
    help_lines: list[str] | None = None,
    confirm_label: str = "确认导出",
    cancel_label: str = "取消",
) -> bool:
    """显示确认对话框并返回是否确认。可自定义按钮文案。"""
    items = [
        MenuItem("__confirm__", confirm_label),
        MenuItem("__cancel__", cancel_label),
    ]
    index = 0

    def _run(stdscr) -> bool:
        nonlocal index
        curses.curs_set(0)
        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            help_text = help_lines or CONFIRM_HELP_LINES
            content_width, left, top, _ = _layout_frame(height, width, help_text, len(items) + len(lines) + 1, None, [])
            stdscr.addnstr(top, max(0, (width - min(_display_width(title), content_width)) // 2), title, min(content_width, width), curses.A_BOLD)
            for row_offset, line in enumerate(help_text, start=1):
                row = top + row_offset
                if row >= height:
                    break
                centered_line = _truncate(line, content_width)
                line_x = max(0, (width - _display_width(centered_line)) // 2)
                stdscr.addnstr(row, line_x, centered_line, min(content_width, width - line_x), curses.A_BOLD)
            divider_row = top + len(help_text) + 1
            if divider_row < height:
                stdscr.addnstr(divider_row, left, "─" * max(0, content_width), content_width)
            row = divider_row + 1
            for line in lines:
                if row >= height - 4:
                    break
                stdscr.addnstr(row, left, _truncate(line, content_width), content_width)
                row += 1
            row += 2
            for offset, item in enumerate(items):
                current_row = row + offset
                if current_row >= height:
                    break
                prefix = ">" if offset == index else " "
                attrs = curses.A_REVERSE if offset == index else 0
                stdscr.addnstr(current_row, left, _truncate(f"{prefix} {item.title}", content_width), content_width, attrs)
            key = stdscr.getch()
            if key == curses.KEY_UP:
                index = max(0, index - 1)
            elif key == curses.KEY_DOWN:
                index = min(len(items) - 1, index + 1)
            elif key in (10, 13):
                return items[index].key == "__confirm__"
            elif key == ord("q"):
                return False

    return curses.wrapper(_run)


def run_select_list(
    title: str,
    lines: list[str],
    *,
    initial_index: int = 0,
    help_lines: list[str] | None = None,
    filter_text: str = "",
    empty_message: str = "暂无可选项",
) -> tuple[int | None, str]:
    """显示可过滤列表，并返回选中项索引与当前过滤词。"""
    index = max(0, min(initial_index, len(lines) - 1)) if lines else 0
    filter_buf = list(filter_text)
    cursor_pos = len(filter_buf)
    in_filter_mode = False

    def _apply_filter(src_lines: list[str], ft: str) -> list[str]:
        if not ft:
            return src_lines
        ft_lower = ft.lower()
        return [line for line in src_lines if ft_lower in line.lower()]

    def _run(stdscr) -> tuple[int | None, str]:
        nonlocal index, filter_buf, cursor_pos, in_filter_mode
        curses.curs_set(1)
        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            current_filter = "".join(filter_buf)
            filtered = _apply_filter(lines, current_filter)
            help_text = help_lines or SELECT_HELP_LINES
            content_width, left, top, divider_row = _layout_frame(height, width, help_text, len(filtered) + 2, None, [])
            stdscr.addnstr(top, max(0, (width - min(_display_width(title), content_width)) // 2), title, min(content_width, width), curses.A_BOLD)
            for row_offset, line in enumerate(help_text, start=1):
                row = top + row_offset
                if row >= height:
                    break
                centered_line = _truncate(line, content_width)
                line_x = max(0, (width - _display_width(centered_line)) // 2)
                stdscr.addnstr(row, line_x, centered_line, min(content_width, width - line_x), curses.A_BOLD)
            if divider_row < height:
                stdscr.addnstr(divider_row, left, "─" * max(0, content_width), content_width)
            row = divider_row + 1
            if in_filter_mode:
                prompt = f"过滤 [{current_filter}]" if current_filter else "过滤 []"
                stdscr.addnstr(height - 2, left, _truncate(prompt, content_width), content_width, curses.A_DIM)
                stdscr.addnstr(height - 1, left, _truncate("".join(filter_buf), content_width), content_width)
                stdscr.move(height - 1, min(left + cursor_pos, max(left, left + content_width - 1)))
            elif current_filter:
                stdscr.addnstr(row, left, _truncate(f"过滤: {current_filter} ({len(filtered)}/{len(lines)})", content_width), content_width, curses.A_DIM)
                row += 1
            if not filtered:
                stdscr.addnstr(row, left, _truncate(empty_message, content_width), content_width, curses.A_DIM)
                row += 1
                curses.curs_set(0)
                key = stdscr.getch()
                curses.curs_set(1)
                if key == ord("q"):
                    return None, current_filter
                if key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
                    if filter_buf:
                        filter_buf.pop()
                    else:
                        in_filter_mode = False
                elif key == 27:
                    filter_buf = []
                    cursor_pos = 0
                    in_filter_mode = False
                elif key in (10, 13):
                    return None, current_filter
                elif isinstance(key, str) and key.isprintable():
                    filter_buf.insert(cursor_pos, key)
                    cursor_pos += 1
                index = 0
                continue
            safe_index = max(0, min(index, len(filtered) - 1))
            for current_row, line in enumerate(filtered, start=row):
                if current_row >= height:
                    break
                prefix = ">" if current_row - row == safe_index else " "
                attrs = curses.A_REVERSE if current_row - row == safe_index else 0
                stdscr.addnstr(current_row, left, _truncate(f"{prefix} {line}", content_width), content_width, attrs)
            if in_filter_mode:
                text = "".join(filter_buf)
                stdscr.addnstr(height - 1, left, _truncate(text, content_width), content_width)
                stdscr.move(height - 1, min(left + cursor_pos, max(left, left + content_width - 1)))
            key = stdscr.getch()
            if in_filter_mode:
                if key in (10, 13):
                    return None, current_filter
                if key == 27:
                    filter_buf = []
                    cursor_pos = 0
                    in_filter_mode = False
                    curses.curs_set(0)
                    continue
                if key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
                    if filter_buf:
                        filter_buf.pop()
                        cursor_pos -= 1
                    continue
                if key == curses.KEY_DC:
                    if cursor_pos < len(filter_buf):
                        del filter_buf[cursor_pos]
                    continue
                if key == curses.KEY_LEFT:
                    cursor_pos = max(0, cursor_pos - 1)
                    continue
                if key == curses.KEY_RIGHT:
                    cursor_pos = min(len(filter_buf), cursor_pos + 1)
                    continue
                if isinstance(key, str) and key.isprintable():
                    filter_buf.insert(cursor_pos, key)
                    cursor_pos += 1
                    continue
                if key == curses.KEY_UP:
                    curses.curs_set(0)
                    in_filter_mode = False
                    index = max(0, index - 1)
                    continue
                if key == curses.KEY_DOWN:
                    curses.curs_set(0)
                    in_filter_mode = False
                    index = min(len(filtered) - 1, index + 1)
                    continue
                continue
            if key == curses.KEY_UP:
                index = max(0, index - 1)
            elif key == curses.KEY_DOWN:
                index = min(len(filtered) - 1, index + 1)
            elif key in (10, 13):
                return safe_index, current_filter
            elif key == ord("q"):
                return None, current_filter
            elif key == ord("/") or key == ord("?"):
                curses.curs_set(1)
                in_filter_mode = True
                filter_buf = []
                cursor_pos = 0
            elif key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
                if filter_buf:
                    filter_buf.pop()
                elif current_filter:
                    filter_buf = list(current_filter[:-1])
                index = 0
            elif isinstance(key, str) and key.isprintable():
                curses.curs_set(1)
                in_filter_mode = True
                filter_buf.append(key)
                cursor_pos = len(filter_buf)
                index = 0

    return curses.wrapper(_run)


def show_message(title: str, lines: list[str], help_lines: list[str] | None = None) -> None:
    """显示提示信息并等待用户返回。"""
    def _run(stdscr) -> None:
        curses.curs_set(0)
        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            help_text = help_lines or MESSAGE_HELP_LINES
            content_width, left, top, divider_row = _layout_frame(height, width, help_text, len(lines), None, [])
            stdscr.addnstr(top, max(0, (width - min(_display_width(title), content_width)) // 2), title, min(content_width, width), curses.A_BOLD)
            for row_offset, line in enumerate(help_text, start=1):
                row = top + row_offset
                if row >= height:
                    break
                centered_line = _truncate(line, content_width)
                line_x = max(0, (width - _display_width(centered_line)) // 2)
                stdscr.addnstr(row, line_x, centered_line, min(content_width, width - line_x), curses.A_BOLD)
            if divider_row < height:
                stdscr.addnstr(divider_row, left, "─" * max(0, content_width), content_width)
            row = divider_row + 1
            for line in lines:
                if row >= height:
                    break
                attr = curses.A_BOLD if "限流" in line or "429" in line else 0
                stdscr.addnstr(row, left, _truncate(line, content_width), content_width, attr)
                row += 1
            key = stdscr.getch()
            if key != -1:
                return None

    curses.wrapper(_run)


def run_waiting_message(title: str, lines: list[str], worker) -> object:
    """显示等待界面并在后台执行任务。"""
    result: dict[str, object] = {"value": None, "error": None}

    def _target() -> None:
        try:
            result["value"] = worker()
        except Exception as exc:  # noqa: BLE001
            result["error"] = exc

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()

    def _run(stdscr):
        curses.curs_set(0)
        frame_index = 0
        while thread.is_alive():
            stdscr.clear()
            height, width = stdscr.getmaxyx()
            stdscr.addnstr(0, 0, title, width - 1, curses.A_BOLD)
            stdscr.addnstr(1, 0, "正在处理中，请稍候", width - 1, curses.A_BOLD)
            row = 3
            for line in lines:
                if row >= height:
                    break
                stdscr.addnstr(row, 0, _truncate(line, width - 1), width - 1)
                row += 1
            if row < height:
                stdscr.addnstr(row, 0, WAITING_FRAMES[frame_index % len(WAITING_FRAMES)], width - 1, curses.A_BOLD)
            stdscr.refresh()
            frame_index += 1
            time.sleep(0.18)
        return None

    curses.wrapper(_run)
    if result["error"] is not None:
        raise result["error"]
    return result["value"]


def _render_menu_items(stdscr, items: list[MenuItem], index: int, start_row: int, left: int, content_width: int, height: int, editing_index: int | None = None, edit_chars: list[str] | None = None, edit_cursor: int = 0) -> tuple[tuple[int, int], int]:
    row = start_row
    cursor_pos = (row, left)
    indent_prefix = "  "  # 2 个空格缩进
    for item_index, item in enumerate(items):
        if row >= height:
            break
        selected = item_index == index and item.focusable
        is_editing = editing_index == item_index
        # 根据缩进级别计算前缀
        title_indent = indent_prefix * item.indent
        marker = {
            "bool": "[*]" if item.value.strip() == "开启" else "[ ]",
            "readonly": "   ",
            "submenu": "[>]",
            "section": "   ",
            "separator": "   ",
            "action": "   ",
        }.get(item.item_type, "   ")
        if item.item_type == "separator":
            stdscr.addnstr(row, left, "─" * max(0, content_width), content_width, curses.A_DIM)
            row += 1
            continue
        if item.item_type == "section":
            stdscr.addnstr(row, left, _truncate(title_indent + item.title, content_width), content_width, curses.A_BOLD)
            row += 1
            continue
        prefix = ">" if selected else " "
        value_text = item.value.strip()
        attrs = curses.A_REVERSE if selected and not is_editing else 0
        display_title = title_indent + item.title
        if item.input_style:
            dots = "·" * max(2, 18 - min(_display_width(display_title), 16))
            if is_editing and edit_chars is not None:
                edit_text = "".join(edit_chars)
                label_prefix = f"{prefix} {display_title} {dots} "
                stdscr.addnstr(row, left, _truncate(label_prefix, content_width), content_width, curses.A_REVERSE)
                edit_start_x = left + _display_width(label_prefix)
                edit_width = content_width - _display_width(label_prefix)
                stdscr.addnstr(row, edit_start_x, _truncate(edit_text, edit_width), edit_width, curses.A_UNDERLINE)
                cursor_display_pos = _display_width("".join(edit_chars[:edit_cursor]))
                cursor_pos = (row, edit_start_x + min(cursor_display_pos, edit_width))
            else:
                label = f"{prefix} {display_title} {dots} {value_text}" if value_text else f"{prefix} {display_title}"
                stdscr.addnstr(row, left, _truncate(label, content_width), content_width, attrs)
            row += 1
            continue
        elif item.item_type == "submenu":
            dots = "·" * max(2, 18 - min(_display_width(display_title), 16))
            detail = value_text or ""
            label = f"{prefix} {display_title} {dots} {detail} ›" if detail else f"{prefix} {display_title} {dots} ›"
        else:
            marker_str = marker.strip()
            if marker_str:
                label = f"{prefix} {marker} {display_title}"
            else:
                label = f"{prefix} {display_title}"
            if value_text:
                label = f"{label}: {value_text}"
        if item.item_type == "readonly":
            color_attrs = curses.A_DIM | attrs
            if "限流" in value_text or "429" in value_text or "限流" in item.title:
                color_attrs = curses.A_BOLD | attrs
                if curses.has_colors():
                    try:
                        curses.start_color()
                        curses.use_default_colors()
                        curses.init_pair(2, curses.COLOR_YELLOW, -1)
                        color_attrs |= curses.color_pair(2)
                    except curses.error:
                        pass
            elif "失败" in value_text or "失败" in item.title:
                color_attrs = curses.A_BOLD | attrs
                if curses.has_colors():
                    try:
                        curses.start_color()
                        curses.use_default_colors()
                        curses.init_pair(1, curses.COLOR_RED, -1)
                        color_attrs |= curses.color_pair(1)
                    except curses.error:
                        pass
            elif "正常" in value_text or "已刷新" in value_text:
                color_attrs = curses.A_BOLD | attrs
                if curses.has_colors():
                    try:
                        curses.start_color()
                        curses.use_default_colors()
                        curses.init_pair(3, curses.COLOR_GREEN, -1)
                        color_attrs |= curses.color_pair(3)
                    except curses.error:
                        pass
            stdscr.addnstr(row, left, _truncate(label, content_width), content_width, color_attrs)
            row += 1
            continue
        stdscr.addnstr(row, left, _truncate(label, content_width), content_width, attrs)
        row += 1
    return cursor_pos, row


def _render_status_lines(stdscr, status_lines: list[str], content_end: int, left: int, content_width: int, height: int) -> None:
    if not status_lines:
        return
    visible_lines = [_truncate(line, content_width) for line in status_lines if line]
    if not visible_lines:
        return
    start_row = height - len(visible_lines)
    divider_row = start_row - 1
    if divider_row <= content_end or divider_row < 0:
        return
    stdscr.addnstr(divider_row, left, "─" * max(0, content_width), content_width, curses.A_DIM)
    for offset, line in enumerate(visible_lines):
        row = start_row + offset
        if 0 <= row < height:
            attrs = curses.A_DIM
            text = line
            prefix_map = {
                "[RED] ": curses.COLOR_RED,
                "[YELLOW] ": curses.COLOR_YELLOW,
                "[GREEN] ": curses.COLOR_GREEN,
                "[BLUE] ": curses.COLOR_CYAN,
            }
            for prefix, color in prefix_map.items():
                if line.startswith(prefix):
                    text = line[len(prefix):]
                    attrs = curses.A_BOLD
                    if curses.has_colors():
                        try:
                            curses.start_color()
                            curses.use_default_colors()
                            pair_id = {curses.COLOR_RED: 1, curses.COLOR_YELLOW: 2, curses.COLOR_GREEN: 3, curses.COLOR_CYAN: 4}[color]
                            curses.init_pair(pair_id, color, -1)
                            attrs |= curses.color_pair(pair_id)
                        except curses.error:
                            pass
                    break
            stdscr.addnstr(row, left, text, content_width, attrs)


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
    if step == 0:
        return current
    candidate = current
    for _ in range(len(items)):
        candidate += step
        if candidate < 0 or candidate >= len(items):
            return current
        if items[candidate].focusable:
            return candidate
    return current


def _display_width(text: str) -> int:
    width = 0
    for char in text:
        width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
    return width


def _truncate(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."
