from __future__ import annotations

import curses
import threading
import time
import unicodedata
from dataclasses import dataclass, field


@dataclass(slots=True)
class InlineChoice:
    """单个菜单行内的可切换选项。"""
    key: str
    label: str
    checked: bool = False


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
    inline_choices: list[InlineChoice] = field(default_factory=list)
    inline_selected_index: int = 0


DEFAULT_HELP_LINES = ["↑↓ 移动 | ←→ 选择行内项 | Enter 确认/编辑 | Space 切换 | s 手动保存配置 | q 返回"]
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
            help_text = _menu_help_lines(help_lines, editing_index is not None)
            edit_cursor_pos = _render_menu_frame(
                stdscr,
                title=title,
                items=items,
                lines=lines,
                help_text=help_text,
                transient_lines=transient_lines,
                index=index,
                editing_index=editing_index,
                edit_chars=edit_chars,
                edit_cursor=edit_cursor,
                height=height,
                width=width,
            )
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
                action, editing_index, edit_chars, edit_cursor, index = _handle_editing_key(
                    key=key,
                    items=items,
                    editing_index=editing_index,
                    edit_chars=edit_chars,
                    edit_cursor=edit_cursor,
                    index=index,
                )
                if action is not None:
                    curses.curs_set(0)
                    return action
                continue
            action, index, editing_index, edit_chars, edit_cursor = _handle_menu_key(
                key=key,
                items=items,
                index=index,
            )
            if editing_index is not None:
                curses.curs_set(1)
                continue
            if action is not None:
                if action == "__exit__":
                    return None
                return action

    return curses.wrapper(_render)


def _menu_help_lines(help_lines: list[str] | None, editing: bool) -> list[str]:
    if help_lines is not None:
        return help_lines
    return EDIT_HELP_LINES if editing else DEFAULT_HELP_LINES


def _render_menu_frame(
    stdscr,
    *,
    title: str,
    items: list[MenuItem],
    lines: list[str],
    help_text: list[str],
    transient_lines: list[str] | None,
    index: int,
    editing_index: int | None,
    edit_chars: list[str],
    edit_cursor: int,
    height: int,
    width: int,
) -> tuple[int, int]:
    content_width, left, top, divider_row = _layout_frame(height, width, help_text, len(items), transient_lines, lines)
    _render_menu_header(stdscr, title=title, help_text=help_text, top=top, width=width, content_width=content_width)
    if divider_row < height:
        stdscr.addnstr(divider_row, left, "─" * max(0, content_width), content_width)
    row = divider_row + 1
    row = _render_transient_lines(stdscr, transient_lines=transient_lines, row=row, left=left, content_width=content_width, height=height)
    edit_cursor_pos, menu_end_row = _render_menu_items(
        stdscr,
        items,
        index,
        row,
        left,
        content_width,
        height,
        editing_index,
        edit_chars,
        edit_cursor,
    )
    _render_status_lines(stdscr, lines, menu_end_row, left, content_width, height)
    return edit_cursor_pos


def _render_menu_header(stdscr, *, title: str, help_text: list[str], top: int, width: int, content_width: int) -> None:
    stdscr.addnstr(top, max(0, (width - min(_display_width(title), content_width)) // 2), title, min(content_width, width), curses.A_BOLD)
    for offset, line in enumerate(help_text, start=1):
        row = top + offset
        centered_line = _truncate(line, content_width)
        line_x = max(0, (width - _display_width(centered_line)) // 2)
        stdscr.addnstr(row, line_x, centered_line, min(content_width, width - line_x), curses.A_BOLD)


def _render_framed_header(stdscr, *, title: str, help_text: list[str], width: int, content_width: int, top: int, left: int, height: int) -> int:
    _render_menu_header(stdscr, title=title, help_text=help_text, top=top, width=width, content_width=content_width)
    divider_row = top + len(help_text) + 1
    if divider_row < height:
        stdscr.addnstr(divider_row, left, "─" * max(0, content_width), content_width)
    return divider_row


def _render_transient_lines(stdscr, *, transient_lines: list[str] | None, row: int, left: int, content_width: int, height: int) -> int:
    if not transient_lines:
        return row
    for line in transient_lines:
        if row >= height:
            break
        stdscr.addnstr(row, left + 2, _truncate(line, max(0, content_width - 2)), max(0, content_width - 2), curses.A_DIM)
        row += 1
    if row < height:
        row += 1
    return row


def _handle_editing_key(*, key, items: list[MenuItem], editing_index: int, edit_chars: list[str], edit_cursor: int, index: int) -> tuple[str | None, int | None, list[str], int, int]:
    if key in ("\n", "\r"):
        result = "".join(edit_chars).strip()
        item_key = items[editing_index].key
        return f"{item_key}:{result}", None, [], 0, index
    if key == "\x1b":
        return None, None, [], 0, index
    if key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
        if edit_cursor > 0:
            del edit_chars[edit_cursor - 1]
            edit_cursor -= 1
        return None, editing_index, edit_chars, edit_cursor, index
    if key == curses.KEY_DC:
        if edit_cursor < len(edit_chars):
            del edit_chars[edit_cursor]
        return None, editing_index, edit_chars, edit_cursor, index
    if key == curses.KEY_LEFT:
        return None, editing_index, edit_chars, max(0, edit_cursor - 1), index
    if key == curses.KEY_RIGHT:
        return None, editing_index, edit_chars, min(len(edit_chars), edit_cursor + 1), index
    if key == curses.KEY_UP:
        return None, None, [], 0, _move_focus(items, index, -1)
    if key == curses.KEY_DOWN:
        return None, None, [], 0, _move_focus(items, index, 1)
    if isinstance(key, str) and key.isprintable():
        edit_chars.insert(edit_cursor, key)
        edit_cursor += 1
    return None, editing_index, edit_chars, edit_cursor, index


def _handle_menu_key(*, key, items: list[MenuItem], index: int) -> tuple[str | None, int, int | None, list[str], int]:
    if key == curses.KEY_UP:
        return None, _move_focus(items, index, -1), None, [], 0
    if key == curses.KEY_DOWN:
        return None, _move_focus(items, index, 1), None, [], 0
    if key == curses.KEY_LEFT and 0 <= index < len(items) and items[index].inline_choices:
        items[index].inline_selected_index = max(0, items[index].inline_selected_index - 1)
        return None, index, None, [], 0
    if key == curses.KEY_RIGHT and 0 <= index < len(items) and items[index].inline_choices:
        items[index].inline_selected_index = min(
            len(items[index].inline_choices) - 1,
            items[index].inline_selected_index + 1,
        )
        return None, index, None, [], 0
    if key in (10, 13):
        if 0 <= index < len(items) and items[index].focusable:
            item = items[index]
            if item.inline_choices:
                selected_index = max(0, min(item.inline_selected_index, len(item.inline_choices) - 1))
                return item.inline_choices[selected_index].key, index, None, [], 0
            if item.input_style:
                initial = item.edit_value if item.edit_value is not None else item.value
                return None, index, index, list(initial), len(initial)
            return item.key, index, None, [], 0
        return None, index, None, [], 0
    if key == ord("q"):
        return "__exit__", index, None, [], 0
    if key == ord("s"):
        return "save", index, None, [], 0
    if key == ord(" ") and 0 <= index < len(items):
        item = items[index]
        if item.inline_choices:
            selected_index = max(0, min(item.inline_selected_index, len(item.inline_choices) - 1))
            return item.inline_choices[selected_index].key, index, None, [], 0
        if item.item_type in {"bool", "check"}:
            return item.key, index, None, [], 0
    return None, index, None, [], 0


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
            divider_row = _render_framed_header(
                stdscr,
                title=title,
                help_text=help_text,
                width=width,
                content_width=content_width,
                top=top,
                left=left,
                height=height,
            )
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
            divider_row = _render_framed_header(
                stdscr,
                title=title,
                help_text=help_text,
                width=width,
                content_width=content_width,
                top=top,
                left=left,
                height=height,
            )
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
            content_width, left, top, _ = _layout_frame(height, width, help_text, len(lines), None, [])
            divider_row = _render_framed_header(
                stdscr,
                title=title,
                help_text=help_text,
                width=width,
                content_width=content_width,
                top=top,
                left=left,
                height=height,
            )
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
    indent_prefix = "    "  # 4 个空格缩进
    for item_index, item in enumerate(items):
        if row >= height:
            break
        selected = item_index == index and item.focusable
        is_editing = editing_index == item_index
        # 根据缩进级别计算前缀
        title_indent = indent_prefix * item.indent
        marker = {
            "bool": "[*]" if item.value.strip() == "开启" else "[ ]",
            "check": "[*]" if item.value.strip() == "开启" else "[ ]",
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
        display_title = item.title
        if item.input_style:
            cursor_pos = _render_input_menu_item(
                stdscr,
                item=item,
                row=row,
                left=left,
                content_width=content_width,
                prefix=prefix,
                marker=marker,
                title_indent=title_indent,
                value_text=value_text,
                attrs=attrs,
                is_editing=is_editing,
                edit_chars=edit_chars,
                edit_cursor=edit_cursor,
            )
            row += 1
            continue
        elif item.inline_choices:
            cursor_pos = _render_inline_choice_menu_item(
                stdscr,
                item=item,
                row=row,
                left=left,
                content_width=content_width,
                prefix=prefix,
                title_indent=title_indent,
                attrs=attrs,
                selected=selected,
            )
            row += 1
            continue
        elif item.item_type == "submenu":
            dots = "·" * max(2, 18 - min(_display_width(display_title), 16))
            detail = value_text or ""
            label = f"{prefix} {display_title} {dots} {detail} ›" if detail else f"{prefix} {display_title} {dots} ›"
        else:
            label = _build_basic_menu_label(
                prefix=prefix,
                marker=marker,
                title_indent=title_indent,
                display_title=display_title,
                value_text=value_text,
                item_type=item.item_type,
            )
        if item.item_type == "readonly":
            stdscr.addnstr(row, left, _truncate(label, content_width), content_width, _readonly_attrs(item.title, value_text, attrs))
            row += 1
            continue
        _render_plain_menu_item(stdscr, row=row, left=left, content_width=content_width, label=label, attrs=attrs)
        row += 1
    return cursor_pos, row


def _render_input_menu_item(
    stdscr,
    *,
    item: MenuItem,
    row: int,
    left: int,
    content_width: int,
    prefix: str,
    marker: str,
    title_indent: str,
    value_text: str,
    attrs: int,
    is_editing: bool,
    edit_chars: list[str] | None,
    edit_cursor: int,
) -> tuple[int, int]:
    dots = "·" * max(2, 18 - min(_display_width(item.title), 16))
    marker_str = marker.strip()
    if marker_str:
        base = f"{title_indent}{prefix} {marker} {item.title}"
    else:
        base = f"{title_indent}{prefix} {item.title}"
    if is_editing and edit_chars is not None:
        edit_text = "".join(edit_chars)
        label_prefix = f"{base} {dots} "
        stdscr.addnstr(row, left, _truncate(label_prefix, content_width), content_width, curses.A_REVERSE)
        edit_start_x = left + _display_width(label_prefix)
        edit_width = content_width - _display_width(label_prefix)
        stdscr.addnstr(row, edit_start_x, _truncate(edit_text, edit_width), edit_width, curses.A_UNDERLINE)
        cursor_display_pos = _display_width("".join(edit_chars[:edit_cursor]))
        return row, edit_start_x + min(cursor_display_pos, edit_width)
    label = f"{base} {dots} {value_text}" if value_text else base
    stdscr.addnstr(row, left, _truncate(label, content_width), content_width, attrs)
    return row, left


def _render_inline_choice_menu_item(
    stdscr,
    *,
    item: MenuItem,
    row: int,
    left: int,
    content_width: int,
    prefix: str,
    title_indent: str,
    attrs: int,
    selected: bool,
) -> tuple[int, int]:
    if item.title:
        label = f"{title_indent}{prefix} {item.title}"
    else:
        label = title_indent
    stdscr.addnstr(row, left, _truncate(label, content_width), content_width, attrs)
    start_x = left + min(_display_width(label), max(0, content_width - 1))
    cell_width = max((min(18, _display_width(f"[ ] {choice.label}") + 4) for choice in item.inline_choices), default=12)
    for choice_index, choice in enumerate(item.inline_choices):
        text = f"{'[*]' if choice.checked else '[ ]'} {choice.label}"
        choice_attr = curses.A_REVERSE if selected and choice_index == item.inline_selected_index else 0
        remaining = max(0, left + content_width - start_x)
        if remaining <= 0:
            break
        padded = text.ljust(cell_width)
        stdscr.addnstr(row, start_x, _truncate(padded, remaining), remaining, choice_attr)
        start_x += cell_width + 2
    return row, left


def _build_basic_menu_label(*, prefix: str, marker: str, title_indent: str, display_title: str, value_text: str, item_type: str) -> str:
    marker_str = marker.strip()
    if marker_str:
        label = f"{title_indent}{prefix} {marker} {display_title}"
    else:
        label = f"{title_indent}{prefix} {display_title}"
    if value_text and item_type not in {"check"}:
        label = f"{label}: {value_text}"
    return label


def _render_plain_menu_item(stdscr, *, row: int, left: int, content_width: int, label: str, attrs: int) -> None:
    stdscr.addnstr(row, left, _truncate(label, content_width), content_width, attrs)


def _readonly_attrs(title: str, value_text: str, attrs: int) -> int:
    if "限流" in value_text or "429" in value_text or "限流" in title:
        return _status_attr(curses.COLOR_YELLOW, attrs)
    if "失败" in value_text or "失败" in title:
        return _status_attr(curses.COLOR_RED, attrs)
    if "正常" in value_text or "已刷新" in value_text:
        return _status_attr(curses.COLOR_GREEN, attrs)
    return curses.A_DIM | attrs


def _status_attr(color: int, attrs: int) -> int:
    color_attrs = curses.A_BOLD | attrs
    if curses.has_colors():
        try:
            curses.start_color()
            curses.use_default_colors()
            pair_id = {
                curses.COLOR_RED: 1,
                curses.COLOR_YELLOW: 2,
                curses.COLOR_GREEN: 3,
                curses.COLOR_CYAN: 4,
            }[color]
            curses.init_pair(pair_id, color, -1)
            color_attrs |= curses.color_pair(pair_id)
        except curses.error:
            pass
    return color_attrs


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
            text, attrs = _status_line_display(line)
            stdscr.addnstr(row, left, text, content_width, attrs)


def _status_line_display(line: str) -> tuple[str, int]:
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
            attrs = _status_attr(color, 0)
            break
    return text, attrs


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
