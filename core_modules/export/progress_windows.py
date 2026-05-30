"""Windows 导出进度界面渲染。"""

from __future__ import annotations

import curses
import threading
from dataclasses import replace
from io import StringIO

from core_modules.console.menu_windows import (
    _enable_keypad,
    _is_down_key,
    _is_enter_key,
    _is_left_key,
    _is_right_key,
    _is_screen_too_small,
    _is_up_key,
    _read_key,
    _render_screen_too_small,
    _set_cursor,
)
from core_modules.export.models import ProgressSnapshot
from core_modules.export.progress import _BaseExportProgressUI, _display_width, _fit


class ExportProgressUI(_BaseExportProgressUI):
    """Windows curses 导出进度 UI。"""

    def _build_progress_bar(self, snapshot: ProgressSnapshot, width: int) -> str:
        """构造带颜色的进度条文本，确保 Windows 宽字符列宽不越界。"""
        total = max(snapshot.total_docs, 1)
        processed = min(snapshot.processed_docs, total)
        ratio = processed / total
        label = f"[{processed}/{snapshot.total_docs}] {ratio * 100:5.1f}%"
        bar_width = _windows_progress_bar_width(width, label)
        filled = min(bar_width, int(bar_width * ratio))
        filled_bar = self._colorize("█" * filled, self.GREEN)
        empty_bar = self._colorize("░" * (bar_width - filled), self._dim_gray())
        return f"进度 {filled_bar}{empty_bar} {label}"

    def _plain_progress_bar(self, snapshot: ProgressSnapshot, width: int) -> str:
        """构造纯文本进度条，确保 Windows 宽字符列宽不越界。"""
        total = max(snapshot.total_docs, 1)
        processed = min(snapshot.processed_docs, total)
        ratio = processed / total
        label = f"[{processed}/{snapshot.total_docs}] {ratio * 100:5.1f}%"
        bar_width = _windows_progress_bar_width(width, label)
        filled = min(bar_width, int(bar_width * ratio))
        return f"进度 {'█' * filled}{'░' * (bar_width - filled)} {label}"

    def _run_curses(self, stdscr, thread: threading.Thread, result: dict[str, object], on_complete) -> None:
        """运行 Windows curses 主循环。"""
        _enable_keypad(stdscr)
        _set_cursor(0)
        self._init_curses_colors(curses)
        _reset_progress_screen(stdscr)
        stdscr.timeout(100)
        completion_built = False
        while True:
            height, width = stdscr.getmaxyx()
            if _is_screen_too_small(height, width):
                _render_screen_too_small(stdscr, title="导出进度", height=height, width=width)
                stdscr.refresh()
                key = _read_key(stdscr)
                if key == -1:
                    continue
                if key == 3:
                    raise KeyboardInterrupt
                continue
            snapshot = self.latest_snapshot
            if not thread.is_alive() and not self._finished:
                self._finished = True
                snapshot = replace(snapshot, current_stage="已完成")
                self.latest_snapshot = snapshot
            if self._finished and not completion_built and result["error"] is None and result["value"] is not None and on_complete is not None:
                self.completion_lines = list(on_complete(result["value"]))
                completion_built = True
            self._render_curses(stdscr, snapshot)
            key = _read_key(stdscr)
            if key == -1:
                continue
            if key == 3:
                raise KeyboardInterrupt
            if _is_left_key(key):
                self._move_focus(snapshot, -1)
            elif _is_right_key(key):
                self._move_focus(snapshot, 1)
            elif _is_up_key(key):
                self._scroll_active_section(snapshot, -1)
            elif _is_down_key(key):
                self._scroll_active_section(snapshot, 1)
            elif _is_page_up_key(key):
                self._scroll_active_section(snapshot, -self.HISTORY_VISIBLE_ROWS)
            elif _is_page_down_key(key):
                self._scroll_active_section(snapshot, self.HISTORY_VISIBLE_ROWS)
            elif (key == ord(" ") or _is_enter_key(key)) and self._is_return_focused(snapshot):
                break

    def _render_curses(self, stdscr, snapshot: ProgressSnapshot) -> None:
        """绘制单帧 Windows curses 界面。"""
        _clear_progress_screen(stdscr, force=True)
        height, width = stdscr.getmaxyx()
        help_lines = (
            ["←→ 切换区块/返回 | ↑↓ 滚动区块 | PgUp/PgDn 快速滚动"]
            if self._finished
            else ["Ctrl+C 退出确认 | ←→ 切换区块 | ↑↓ 滚动区块 | PgUp/PgDn 快速滚动"]
        )
        content_width = min(width - 1, max(60, min(128, width - 4)))
        left = max(0, (width - content_width) // 2)
        top_margin = max(1, height // 8)
        title = "语雀导出"
        title_x = max(0, (width - _display_width(title)) // 2)
        _draw_progress_text(stdscr, top_margin, title_x, title, width=min(content_width, width - title_x), attrs=self._curses_attr(curses, "title"))

        row = top_margin + 1
        for line in help_lines:
            line_x = max(0, (width - _display_width(line)) // 2)
            if row < height:
                _draw_progress_text(stdscr, row, line_x, line, width=min(content_width, width - line_x), attrs=self._curses_attr(curses, "help"))
            row += 1

        if row < height:
            _draw_progress_text(stdscr, row, left, "─" * max(0, content_width), width=content_width, attrs=self._curses_attr(curses, "divider"))
        row += 1

        fixed_lines: list[tuple[str, int]] = [
            (self._plain_progress_bar(snapshot, content_width), self._curses_attr(curses, "progress")),
            (f"阶段: {snapshot.current_stage}", self._status_attr(snapshot.current_stage, curses)),
            (f"当前: {snapshot.current_doc_title or '—'}", self._curses_attr(curses, "current_doc")),
        ]
        doc_stats = self._plain_current_doc_stats(snapshot)
        if doc_stats:
            fixed_lines.append((doc_stats, curses.A_DIM))
        fixed_lines.extend(
            [
                ("─" * content_width, self._curses_attr(curses, "divider")),
                ("── 统计 ──", self._curses_attr(curses, "section")),
                (self._plain_stats_line(snapshot), self._curses_attr(curses, "stats")),
            ]
        )
        rate_line = self._plain_rate_limit_line(snapshot)
        if rate_line:
            fixed_lines.append(("── 限流 ──", self._curses_attr(curses, "section")))
            fixed_lines.append((rate_line, self._curses_attr(curses, "rate_limit")))
        scroll_sections = self._build_scroll_sections(snapshot, content_width)
        section_title, section_lines = self._primary_section_lines(snapshot)
        fixed_lines.extend(
            [
                ("─" * content_width, self._curses_attr(curses, "divider")),
                (f"── {section_title} ──", self._curses_attr(curses, "section")),
            ]
        )
        fixed_lines.extend((line, self._curses_attr(curses, "active")) for line in section_lines)

        footer_lines = self._build_footer_lines(snapshot)
        available_section_rows = self.HISTORY_VISIBLE_ROWS

        for text, attr in fixed_lines:
            if row >= height:
                break
            _draw_progress_text(stdscr, row, left, text, width=content_width, attrs=attr)
            row += 1

        for section_index, (section_key, title_text, section_lines, role) in enumerate(scroll_sections):
            if row >= height:
                break
            title_attr = self._curses_attr(curses, "section")
            if section_index == self.section_focus:
                title_attr |= curses.A_REVERSE
            visible_lines, display_label = self._slice_display_lines(section_key, section_lines, available_section_rows)
            _draw_progress_text(stdscr, row, left, f"── {title_text} ── {display_label}", width=content_width, attrs=title_attr)
            row += 1
            for line in visible_lines:
                if row >= height:
                    break
                line_attr = self._curses_attr(curses, role)
                if section_key == "history":
                    line_attr = self._curses_attr(curses, "warning") if "[!]" in line else self._curses_attr(curses, "error")
                _draw_progress_text(stdscr, row, left, line, width=content_width, attrs=line_attr)
                row += 1

        if row < height:
            _draw_progress_text(stdscr, row, left, "─" * max(0, content_width), width=content_width, attrs=self._curses_attr(curses, "divider"))
            row += 1

        for text, attr in footer_lines:
            if row >= height:
                break
            _draw_progress_text(stdscr, row, left, text, width=content_width, attrs=attr)
            row += 1

        if self._finished and row < height:
            button_attr = self._build_return_button(curses, focused=self._is_return_focused(snapshot))
            button_text = " 返回 "
            button_x = max(0, (width - _display_width(button_text)) // 2)
            _draw_progress_text(stdscr, row, button_x, button_text, width=min(content_width, width - button_x), attrs=button_attr)
            row += 1

        _refresh_progress_screen(stdscr)

    def _supports_interactive_curses(self) -> bool:
        """Windows 不依赖 TERM，只要 stdout 是 TTY 即可使用 curses。"""
        if isinstance(self.stream, StringIO):
            return False
        if not hasattr(self.stream, "isatty") or not self.stream.isatty():
            return False
        return True

    def _footer_attr(self) -> int:
        """返回页脚统一使用的样式。"""
        return curses.A_DIM


def _is_page_down_key(key) -> bool:
    return key == getattr(curses, "KEY_NPAGE", 338) or key == 338


def _is_page_up_key(key) -> bool:
    return key == getattr(curses, "KEY_PPAGE", 339) or key == 339


def _reset_progress_screen(stdscr) -> None:
    """接管窗口时强制刷新物理屏幕，避免残留上一层菜单。"""
    try:
        curses.flushinp()
    except curses.error:
        pass
    _clear_progress_screen(stdscr, force=True)
    _refresh_progress_screen(stdscr)


def _clear_progress_screen(stdscr, *, force: bool = False) -> None:
    """清空 curses 窗口；Windows/PDCurses 需要显式铺空白来处理残影。"""
    if force:
        _force_progress_clearok(stdscr)
    try:
        height, width = stdscr.getmaxyx()
    except curses.error:
        height, width = 0, 0
    try:
        stdscr.clear()
    except curses.error:
        try:
            stdscr.erase()
        except curses.error:
            pass
    blank = " " * max(0, width - 1)
    if blank:
        for row in range(height):
            try:
                stdscr.addstr(row, 0, blank)
            except curses.error:
                continue
    _touch_progress_screen(stdscr)


def _refresh_progress_screen(stdscr) -> None:
    """一次性提交当前帧，减少 Windows curses 清屏闪烁和半帧残影。"""
    _touch_progress_screen(stdscr)
    try:
        stdscr.refresh()
    except curses.error:
        try:
            stdscr.noutrefresh()
            curses.doupdate()
        except curses.error:
            pass


def _touch_progress_screen(stdscr) -> None:
    """标记整屏需要重绘，弥补 Windows curses 对空白区域的刷新优化。"""
    try:
        stdscr.redrawwin()
    except (AttributeError, curses.error):
        pass
    try:
        stdscr.touchwin()
    except (AttributeError, curses.error):
        pass


def _force_progress_clearok(stdscr) -> None:
    """同时标记 stdscr 和物理屏幕状态无效，强制 PDCurses 重画。"""
    for screen in (stdscr, getattr(curses, "curscr", None)):
        if screen is None:
            continue
        try:
            screen.clearok(True)
        except (AttributeError, curses.error):
            continue


def _clear_progress_line(stdscr, row: int) -> None:
    """清理整行并标记该行需要刷新。"""
    try:
        stdscr.move(row, 0)
        stdscr.clrtoeol()
    except (AttributeError, curses.error):
        pass
    try:
        stdscr.touchline(row, 1)
    except (AttributeError, curses.error):
        pass


def _draw_progress_text(stdscr, row: int, col: int, text: str, *, width: int, attrs: int = 0) -> None:
    """Windows 进度页专用绘制：按 macOS 路径裁剪写入，并额外清理旧行。"""
    if row < 0 or col < 0 or width <= 0:
        return
    try:
        height, screen_width = stdscr.getmaxyx()
    except curses.error:
        return
    if row >= height or col >= screen_width:
        return
    line_width = max(0, screen_width - 1)
    available = min(width, max(0, line_width - col))
    if available <= 0:
        return
    safe_text = _fit_progress_text(text, available)
    _clear_progress_line(stdscr, row)
    try:
        stdscr.addstr(row, col, safe_text, attrs)
    except curses.error:
        return
    try:
        stdscr.touchline(row, 1)
    except (AttributeError, curses.error):
        pass


def _fit_progress_text(text: str, width: int) -> str:
    """复用共享裁剪逻辑，保证 Windows 可见文本与 macOS 一致。"""
    return _fit(text, width)


def _windows_progress_bar_width(width: int, label: str) -> int:
    """计算 Windows 进度条主体宽度，补足中文“进度”前缀的列宽。"""
    fixed_width = _display_width("进度 ") + _display_width(" ") + _display_width(label)
    return max(10, width - fixed_width)
