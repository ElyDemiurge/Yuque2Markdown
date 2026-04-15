from __future__ import annotations

import curses
from dataclasses import dataclass, field

from core_modules.console.menu import _display_width, _layout_frame, _render_framed_header
from core_modules.export.models import TocNode


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


HELP_LINE_1 = "↑↓ 移动 | ←→ 展开/折叠 | Space 切换 | Enter 确认 | / 过滤 | q 返回"
HELP_LINE_2 = "a 全选可见文档 | n 清空选择 | PgUp/PgDn 翻页 | Esc 清空过滤"


def select_doc_ids(nodes: list[TocNode], initial_selected: set[int] | None = None, summary_lines: list[str] | None = None) -> set[int]:
    state = _SelectorState(root_nodes=nodes)
    state.summary_lines = list(summary_lines or [])
    if initial_selected:
        state.selected = set(initial_selected)
    state.expanded_keys = _collect_expandable_keys(nodes)
    _refresh_items(state)

    def run(stdscr) -> set[int]:
        curses.curs_set(0)
        while True:
            _render(stdscr, state)
            key = stdscr.get_wch()
            if key == curses.KEY_UP:
                _move_cursor(state, -1)
            elif key == curses.KEY_DOWN:
                _move_cursor(state, 1)
            elif key == curses.KEY_LEFT:
                _collapse_current(state)
            elif key == curses.KEY_RIGHT:
                _expand_current(state)
            elif key == curses.KEY_NPAGE:
                _page_down(stdscr, state)
            elif key == curses.KEY_PPAGE:
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
            elif key in ("\n", "\r"):
                return state.selected
            elif key == "q":
                return state.selected

    return curses.wrapper(run)


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


def _flatten_visible(nodes: list[TocNode], expanded_keys: set[str], depth: int = 0, filter_text: str = "") -> list[_MenuItem]:
    items: list[_MenuItem] = []
    query = filter_text.lower().strip()
    for node in nodes:
        key = _node_key(node)
        expanded = key in expanded_keys
        children_items = _flatten_visible(node.children, expanded_keys, depth + 1, filter_text=filter_text) if node.children and expanded else []
        matches_self = not query or query in node.title.lower() or (node.slug and query in node.slug.lower())
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
        stdscr.addnstr(row, left, _truncate(f"过滤: {state.filter_text}", content_width), content_width, curses.A_DIM)
        row += 1
    for line in state.summary_lines[:2]:
        if row >= height:
            break
        stdscr.addnstr(row, left, _truncate(line, content_width), content_width, curses.A_DIM)
        row += 1
    if row < height:
        stdscr.addnstr(row, left, "─" * max(0, content_width), content_width, curses.A_DIM)
        row += 1

    footer = _build_footer_line(state)
    content_height = max(1, height - row - 2)
    total = len(state.items)
    if total == 0:
        stdscr.addnstr(row, left, _truncate("当前过滤条件下没有匹配的文档，按 Esc 清空过滤", content_width), content_width, curses.A_DIM)
        stdscr.addnstr(height - 1, left, _truncate(footer, content_width), content_width, curses.A_DIM)
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
        stdscr.addnstr(current_row, left, label, content_width, attrs)
    if height - 2 >= row:
        stdscr.addnstr(height - 2, left, "─" * max(0, content_width), content_width, curses.A_DIM)
    stdscr.addnstr(height - 1, left, _truncate(footer, content_width), content_width, curses.A_DIM)


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


def _prompt_filter(stdscr, state: _SelectorState) -> None:
    chars = list(state.filter_text)
    cursor = len(chars)
    curses.curs_set(1)
    while True:
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
        prompt = f"过滤: {''.join(chars)}"
        stdscr.addnstr(height - 1, left, _truncate(prompt, content_width), content_width, curses.A_DIM)
        stdscr.move(height - 1, min(left + len("过滤: ") + cursor, max(left, left + content_width - 1)))
        key = stdscr.get_wch()
        if key in ("\n", "\r"):
            state.filter_text = "".join(chars).strip()
            _refresh_items(state)
            curses.curs_set(0)
            return
        if key == "\x1b":
            state.filter_text = ""
            _refresh_items(state)
            curses.curs_set(0)
            return
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
