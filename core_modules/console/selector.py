from __future__ import annotations

import curses
from dataclasses import dataclass, field

from core_modules.console.menu import (
    _apply_text_edit_key,
    _draw_text,
    _display_width,
    _enable_keypad,
    _filter_cursor_x,
    _is_enter_key,
    _is_escape_key,
    _is_screen_too_small,
    _layout_frame,
    _render_framed_header,
    _render_screen_too_small,
)
from core_modules.export.models import TocNode

try:
    from core_modules.console.menu import _read_key as _backend_read_key
except ImportError:  # Unix 后端使用阻塞读取，不提供轮询读键封装。
    _backend_read_key = None

try:
    from core_modules.console.menu import _is_up_key as _backend_is_up_key
    from core_modules.console.menu import _is_down_key as _backend_is_down_key
    from core_modules.console.menu import _is_left_key as _backend_is_left_key
    from core_modules.console.menu import _is_right_key as _backend_is_right_key
except ImportError:  # Unix 后端的 curses 键码可直接比较。
    _backend_is_up_key = None
    _backend_is_down_key = None
    _backend_is_left_key = None
    _backend_is_right_key = None


@dataclass(slots=True)
class _MenuItem:
    key: str
    node: TocNode
    depth: int
    expanded: bool


@dataclass(slots=True)
class _SelectorState:
    root_nodes: list[TocNode]
    selected: set[int] = field(default_factory=set)
    expanded_keys: set[str] = field(default_factory=set)
    items: list[_MenuItem] = field(default_factory=list)
    index: int = 0
    top: int = 0
    summary_lines: list[str] = field(default_factory=list)
    filter_text: str = ""


HELP_LINE_1 = "↑↓ 移动 | ←→ 展开/折叠 | Space 切换 | Enter 确认 | / 过滤 | Esc 返回"
HELP_LINE_2 = "a 全选可见文档 | n 清空选择 | PgUp/PgDn 翻页 | Esc 清空过滤"


def select_doc_ids(nodes: list[TocNode], initial_selected: set[int] | None = None, summary_lines: list[str] | None = None) -> set[int]:
    state = _SelectorState(root_nodes=nodes)
    state.summary_lines = list(summary_lines or [])
    if initial_selected:
        state.selected = set(initial_selected)
    state.expanded_keys = _collect_expandable_keys(nodes)
    _refresh_items(state)

    def run(stdscr) -> set[int]:
        _enable_keypad(stdscr)
        _configure_selector_timeout(stdscr)
        _set_cursor(0)
        while True:
            height, width = stdscr.getmaxyx()
            if _is_screen_too_small(height, width):
                _render_screen_too_small(stdscr, title="选择文档", height=height, width=width)
                stdscr.refresh()
                key = _read_selector_key(stdscr, wide=True)
                if key == -1:
                    continue
                if _is_escape_key(key):
                    return state.selected
                continue
            _render(stdscr, state)
            key = _read_selector_key(stdscr, wide=True)
            if key == -1:
                continue
            if _is_up_key(key):
                _move_cursor(state, -1)
            elif _is_down_key(key):
                _move_cursor(state, 1)
            elif _is_left_key(key):
                _collapse_current(state)
            elif _is_right_key(key):
                _expand_current(state)
            elif _is_page_down_key(key):
                _page_down(stdscr, state)
            elif _is_page_up_key(key):
                _page_up(stdscr, state)
            elif key == "g":
                state.index = 0
            elif key == "G":
                state.index = max(0, len(state.items) - 1)
            elif key == " ":
                _toggle_selection(state)
            elif key == "a":
                _select_all(state)
            elif key == "n":
                state.selected.clear()
            elif key == "/":
                _prompt_filter(stdscr, state)
            elif _is_enter_key(key):
                return state.selected
            elif _is_escape_key(key):
                return state.selected

    return curses.wrapper(run)


def _read_selector_key(stdscr, *, wide: bool = False):
    """读取选择器按键；Windows 轮询无输入时返回 -1 而不是抛出 ``no input``。"""
    if _backend_read_key is not None:
        return _backend_read_key(stdscr, wide=wide)
    try:
        if wide and hasattr(stdscr, "get_wch"):
            return stdscr.get_wch()
        return stdscr.getch()
    except curses.error:
        return -1


def _configure_selector_timeout(stdscr) -> None:
    """Windows 后端使用短轮询；Unix/macOS 保持阻塞读取体验。"""
    try:
        stdscr.timeout(100 if _backend_read_key is not None else -1)
    except (AttributeError, curses.error):
        return


def _set_cursor(visibility: int) -> None:
    try:
        curses.curs_set(visibility)
    except (AttributeError, curses.error):
        return


def _is_up_key(key) -> bool:
    if _backend_is_up_key is not None:
        return _backend_is_up_key(key)
    return key == curses.KEY_UP


def _is_down_key(key) -> bool:
    if _backend_is_down_key is not None:
        return _backend_is_down_key(key)
    return key == curses.KEY_DOWN


def _is_left_key(key) -> bool:
    if _backend_is_left_key is not None:
        return _backend_is_left_key(key)
    return key == curses.KEY_LEFT


def _is_right_key(key) -> bool:
    if _backend_is_right_key is not None:
        return _backend_is_right_key(key)
    return key == curses.KEY_RIGHT


def _is_page_down_key(key) -> bool:
    return key == getattr(curses, "KEY_NPAGE", 338) or key == 338


def _is_page_up_key(key) -> bool:
    return key == getattr(curses, "KEY_PPAGE", 339) or key == 339


def _collect_expandable_keys(nodes: list[TocNode]) -> set[str]:
    keys: set[str] = set()
    for node in nodes:
        key = _node_key(node)
        if node.children:
            keys.add(key)
            keys.update(_collect_expandable_keys(node.children))
    return keys


def _refresh_items(state: _SelectorState) -> None:
    current_key = state.items[state.index].key if state.items and 0 <= state.index < len(state.items) else None
    state.items = _flatten_visible(state.root_nodes, state.expanded_keys, filter_text=state.filter_text)
    if not state.items:
        state.index = 0
        state.top = 0
        return
    if current_key is None:
        state.index = min(state.index, len(state.items) - 1)
        return
    for idx, item in enumerate(state.items):
        if item.key == current_key:
            state.index = idx
            return
    state.index = min(state.index, len(state.items) - 1)


def _flatten_subtree(nodes: list[TocNode], depth: int = 0) -> list[_MenuItem]:
    """展开整棵子树，用于目录名命中过滤词的场景。"""
    items: list[_MenuItem] = []
    for node in nodes:
        key = _node_key(node)
        expanded = bool(node.children)
        items.append(_MenuItem(key=key, node=node, depth=depth, expanded=expanded))
        if node.children:
            items.extend(_flatten_subtree(node.children, depth + 1))
    return items


def _flatten_visible(nodes: list[TocNode], expanded_keys: set[str], depth: int = 0, filter_text: str = "") -> list[_MenuItem]:
    """按展开状态和过滤词生成可见节点列表。

    规则:
        1. 无过滤词时，严格按照用户展开状态渲染。
        2. 过滤词命中目录名时，展开该目录整棵子树。
        3. 过滤词命中深层文档时，即使上层目录原本折叠，也会沿路径自动展开。
    """
    items: list[_MenuItem] = []
    query = filter_text.lower().strip()
    for node in nodes:
        key = _node_key(node)
        matches_self = not query or query in node.title.lower() or (node.slug and query in node.slug.lower())
        expanded = key in expanded_keys
        if not query:
            children_items = _flatten_visible(node.children, expanded_keys, depth + 1, filter_text=filter_text) if node.children and expanded else []
        elif matches_self and node.children:
            children_items = _flatten_subtree(node.children, depth + 1)
            expanded = True
        else:
            children_items = _flatten_visible(node.children, expanded_keys, depth + 1, filter_text=filter_text) if node.children else []
            if children_items:
                expanded = True
        if query and not matches_self and not children_items:
            continue
        items.append(_MenuItem(key=key, node=node, depth=depth, expanded=expanded))
        items.extend(children_items)
    return items


def _render(stdscr, state: _SelectorState) -> None:
    stdscr.clear()
    height, width = stdscr.getmaxyx()
    help_lines = [HELP_LINE_1, HELP_LINE_2]
    content_width, left, top, divider_row = _layout_frame(
        height,
        width,
        help_lines,
        len(state.items) + len(state.summary_lines) + 2,
        None,
        [],
    )
    divider_row = _render_framed_header(
        stdscr,
        title="选择文档",
        help_text=help_lines,
        width=width,
        content_width=content_width,
        top=top,
        left=left,
        height=height,
    )
    row = divider_row + 1
    if state.filter_text:
        _draw_text(stdscr, row, left, f"过滤: {state.filter_text}", width=content_width, attrs=curses.A_DIM)
        row += 1
    for line in state.summary_lines[:2]:
        if row >= height:
            break
        _draw_text(stdscr, row, left, line, width=content_width, attrs=curses.A_DIM)
        row += 1
    if row < height:
        _draw_text(stdscr, row, left, "─" * max(0, content_width), width=content_width, attrs=curses.A_DIM)
        row += 1

    footer = _build_footer_line(state)
    content_height = max(1, height - row - 2)
    total = len(state.items)
    if total == 0:
        _draw_text(stdscr, row, left, "当前过滤条件下没有匹配的文档，按 Esc 清空过滤", width=content_width, attrs=curses.A_DIM)
        _draw_text(stdscr, height - 1, left, footer, width=content_width, attrs=curses.A_DIM)
        return

    if state.index < state.top:
        state.top = state.index
    if state.index >= state.top + content_height:
        state.top = state.index - content_height + 1
    state.top = max(0, min(state.top, max(0, total - content_height)))

    visible = state.items[state.top : state.top + content_height]
    for current_row, item in enumerate(visible, start=row):
        marker = _marker_for_node(item.node, state.selected)
        expand_marker = _expand_marker(item)
        prefix = "  " * item.depth
        suffix = _suffix_for_node(item.node)
        label = _truncate(f"{marker} {expand_marker} {prefix}{item.node.title}{suffix}", content_width)
        attrs = curses.A_REVERSE if state.top + current_row - row == state.index else 0
        _draw_text(stdscr, current_row, left, label, width=content_width, attrs=attrs)
    if height - 2 >= row:
        _draw_text(stdscr, height - 2, left, "─" * max(0, content_width), width=content_width, attrs=curses.A_DIM)
    _draw_text(stdscr, height - 1, left, footer, width=content_width, attrs=curses.A_DIM)


def _truncate(text: str, max_len: int) -> str:
    if max_len <= 0:
        return ""
    if _display_width(text) <= max_len:
        return text
    if max_len == 1:
        return "…"
    result: list[str] = []
    current_width = 0
    for char in text:
        char_width = _display_width(char)
        if current_width + char_width > max_len - 1:
            break
        result.append(char)
        current_width += char_width
    return "".join(result) + "…"


def _node_key(node: TocNode) -> str:
    if node.uuid:
        return f"uuid:{node.uuid}"
    if node.doc_id:
        return f"doc:{node.doc_id}"
    if node.slug:
        return f"slug:{node.slug}"
    if node.url:
        return f"url:{node.url}"
    return f"title:{node.node_type}:{node.title}"


def _marker_for_node(node: TocNode, selected: set[int]) -> str:
    ids = _collect_doc_ids(node)
    if node.node_type == "TITLE":
        if not ids:
            return "[.]"
        selected_count = len(ids & selected)
        if selected_count == 0:
            return "[+]"
        if selected_count == len(ids):
            return "[#]"
        return "[~]"

    if not ids:
        return "[-]"
    selected_count = len(ids & selected)
    if selected_count == 0:
        return "[ ]"
    if selected_count == len(ids):
        return "[x]"
    return "[*]"


def _expand_marker(item: _MenuItem) -> str:
    if not item.node.children:
        return " "
    return "▾" if item.expanded else "▸"


def _build_footer_line(state: _SelectorState) -> str:
    selected_docs = len(state.selected)
    visible_items = len(state.items)
    filter_part = f" | 过滤: {state.filter_text}" if state.filter_text else ""
    return f"已选 {selected_docs} 篇 | 可见 {visible_items} 项{filter_part}"


def _suffix_for_node(node: TocNode) -> str:
    ids = _collect_doc_ids(node)
    if node.node_type == "TITLE":
        return f"  ({len(ids)})"
    if node.node_type == "LINK":
        return "  (链接)"
    return ""


def _collect_doc_ids(node: TocNode) -> set[int]:
    ids: set[int] = set()
    if node.node_type == "DOC" and node.doc_id:
        ids.add(node.doc_id)
    for child in node.children:
        ids.update(_collect_doc_ids(child))
    return ids


def _move_cursor(state: _SelectorState, delta: int) -> None:
    if not state.items:
        return
    state.index = max(0, min(len(state.items) - 1, state.index + delta))


def _visible_content_height(stdscr, state: _SelectorState) -> int:
    height, _ = stdscr.getmaxyx()
    header_rows = 2 + (1 if state.filter_text else 0) + min(2, len(state.summary_lines))
    return max(1, height - header_rows - 2)


def _page_down(stdscr, state: _SelectorState) -> None:
    if not state.items:
        return
    page_size = _visible_content_height(stdscr, state)
    state.index = min(len(state.items) - 1, state.index + page_size)


def _page_up(stdscr, state: _SelectorState) -> None:
    if not state.items:
        return
    page_size = _visible_content_height(stdscr, state)
    state.index = max(0, state.index - page_size)


def _collapse_current(state: _SelectorState) -> None:
    if not state.items:
        return
    item = state.items[state.index]
    if item.node.children and item.expanded:
        state.expanded_keys.discard(item.key)
        _refresh_items(state)
        return
    if item.depth == 0:
        return
    current_depth = item.depth
    for idx in range(state.index - 1, -1, -1):
        if state.items[idx].depth < current_depth:
            state.index = idx
            return


def _expand_current(state: _SelectorState) -> None:
    if not state.items:
        return
    item = state.items[state.index]
    if item.node.children and not item.expanded:
        state.expanded_keys.add(item.key)
        _refresh_items(state)


def _toggle_selection(state: _SelectorState) -> None:
    if not state.items:
        return
    item = state.items[state.index]
    ids = _collect_doc_ids(item.node)
    if not ids:
        return
    if ids.issubset(state.selected):
        state.selected.difference_update(ids)
    else:
        state.selected.update(ids)


def _select_all(state: _SelectorState) -> None:
    state.selected.clear()
    for item in state.items:
        state.selected.update(_collect_doc_ids(item.node))


def _set_filter_text(state: _SelectorState, text: str) -> None:
    normalized = text.strip()
    if state.filter_text == normalized:
        return
    state.filter_text = normalized
    _refresh_items(state)


def _render_filter_prompt(stdscr, *, left: int, height: int, content_width: int, chars: list[str], cursor: int) -> None:
    prompt = f"过滤: {''.join(chars)}"
    _draw_text(stdscr, height - 1, left, " " * max(0, content_width), width=content_width, attrs=curses.A_DIM)
    _draw_text(stdscr, height - 1, left, prompt, width=content_width, attrs=curses.A_DIM)
    try:
        stdscr.move(height - 1, _filter_cursor_x(left, content_width, chars, cursor))
    except curses.error:
        return


def _prompt_filter(stdscr, state: _SelectorState) -> None:
    chars = list(state.filter_text)
    cursor = len(chars)
    _enable_keypad(stdscr)
    _configure_selector_timeout(stdscr)
    while True:
        _set_cursor(1)
        _render(stdscr, state)
        height, width = stdscr.getmaxyx()
        content_width, left, _top, _divider_row = _layout_frame(
            height,
            width,
            [HELP_LINE_1, HELP_LINE_2],
            len(state.items) + len(state.summary_lines) + 2,
            None,
            [],
        )
        _render_filter_prompt(stdscr, left=left, height=height, content_width=content_width, chars=chars, cursor=cursor)
        key = _read_selector_key(stdscr, wide=True)
        if key == -1:
            continue
        if _is_enter_key(key):
            _set_filter_text(state, "".join(chars))
            _set_cursor(0)
            return
        if _is_escape_key(key):
            _set_filter_text(state, "")
            _set_cursor(0)
            return
        chars, cursor, handled = _apply_text_edit_key(key, chars, cursor)
        if handled:
            _set_filter_text(state, "".join(chars))
