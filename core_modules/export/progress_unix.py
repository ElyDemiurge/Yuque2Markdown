"""macOS/Unix 导出进度界面渲染。"""

from __future__ import annotations

import curses
import threading
from dataclasses import replace

from core_modules.console.menu import _is_screen_too_small, _render_screen_too_small
from core_modules.export.models import ProgressSnapshot
from core_modules.export.progress import _BaseExportProgressUI, _display_width, _fit


class ExportProgressUI(_BaseExportProgressUI):
    """macOS/Unix curses 导出进度 UI。"""

    def _run_curses(self, stdscr, thread: threading.Thread, result: dict[str, object], on_complete) -> None:
        """运行 curses 主循环。"""
        curses.curs_set(0)
        self._init_curses_colors(curses)
        stdscr.timeout(150)
        completion_built = False
        while True:
            height, width = stdscr.getmaxyx()
            if _is_screen_too_small(height, width):
                _render_screen_too_small(stdscr, title="导出进度", height=height, width=width)
                stdscr.refresh()
                key = stdscr.getch()
                if key == 3:
                    raise KeyboardInterrupt
                continue
            snapshot = self.latest_snapshot
            if not thread.is_alive() and not self._finished:
                self._finished = True
                snapshot = replace(snapshot, current_stage="已完成")
                self.latest_snapshot = snapshot
            if self._finished and not completion_built and result["error"] is None and result["value"] is not None and on_complete is not None:
                # 导出完成后生成摘要。
                self.completion_lines = list(on_complete(result["value"]))
                completion_built = True
            self._render_curses(stdscr, snapshot)
            if not thread.is_alive():
                stdscr.timeout(-1)
                key = stdscr.getch()
                if key == curses.KEY_LEFT:
                    self._move_focus(snapshot, -1)
                    continue
                if key == curses.KEY_RIGHT:
                    self._move_focus(snapshot, 1)
                    continue
                if key == curses.KEY_UP:
                    self._scroll_active_section(snapshot, -1)
                    continue
                if key == curses.KEY_DOWN:
                    self._scroll_active_section(snapshot, 1)
                    continue
                if key == curses.KEY_PPAGE:
                    self._scroll_active_section(snapshot, -self.HISTORY_VISIBLE_ROWS)
                    continue
                if key == curses.KEY_NPAGE:
                    self._scroll_active_section(snapshot, self.HISTORY_VISIBLE_ROWS)
                    continue
                if key in {10, 13, curses.KEY_ENTER, ord(" ")} and self._is_return_focused(snapshot):
                    break
                continue
            key = stdscr.getch()
            if key == -1:
                continue
            if key == 3:
                raise KeyboardInterrupt
            if key == curses.KEY_LEFT:
                self._move_focus(snapshot, -1)
            elif key == curses.KEY_RIGHT:
                self._move_focus(snapshot, 1)
            elif key == curses.KEY_UP:
                self._scroll_active_section(snapshot, -1)
            elif key == curses.KEY_DOWN:
                self._scroll_active_section(snapshot, 1)
            elif key == curses.KEY_PPAGE:
                self._scroll_active_section(snapshot, -self.HISTORY_VISIBLE_ROWS)
            elif key == curses.KEY_NPAGE:
                self._scroll_active_section(snapshot, self.HISTORY_VISIBLE_ROWS)

    def _render_curses(self, stdscr, snapshot: ProgressSnapshot) -> None:
        """绘制单帧 curses 界面。"""
        stdscr.clear()
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
        stdscr.addnstr(top_margin, title_x, title, min(content_width, width - title_x), self._curses_attr(curses, "title"))

        row = top_margin + 1
        for line in help_lines:
            line_x = max(0, (width - _display_width(line)) // 2)
            if row < height:
                stdscr.addnstr(row, line_x, _fit(line, content_width), min(content_width, width - line_x), self._curses_attr(curses, "help"))
            row += 1

        if row < height:
            stdscr.addnstr(row, left, "─" * max(0, content_width), content_width, self._curses_attr(curses, "divider"))
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
            stdscr.addnstr(row, left, _fit(text, content_width), content_width, attr)
            row += 1

        for section_index, (section_key, title_text, section_lines, role) in enumerate(scroll_sections):
            if row >= height:
                break
            title_attr = self._curses_attr(curses, "section")
            if section_index == self.section_focus:
                title_attr |= curses.A_REVERSE
            visible_lines, display_label = self._slice_display_lines(section_key, section_lines, available_section_rows)
            stdscr.addnstr(row, left, _fit(f"── {title_text} ── {display_label}", content_width), content_width, title_attr)
            row += 1
            for line in visible_lines:
                if row >= height:
                    break
                line_attr = self._curses_attr(curses, role)
                if section_key == "history":
                    line_attr = self._curses_attr(curses, "warning") if "[!]" in line else self._curses_attr(curses, "error")
                stdscr.addnstr(row, left, _fit(line, content_width), content_width, line_attr)
                row += 1

        if row < height:
            stdscr.addnstr(row, left, "─" * max(0, content_width), content_width, self._curses_attr(curses, "divider"))
            row += 1

        for text, attr in footer_lines:
            if row >= height:
                break
            stdscr.addnstr(row, left, _fit(text, content_width), content_width, attr)
            row += 1

        if self._finished and row < height:
            button_text = self._build_return_button(curses, focused=self._is_return_focused(snapshot))
            button_x = max(0, (width - _display_width(" 返回 ")) // 2)
            stdscr.addnstr(row, button_x, " 返回 ", min(content_width, width - button_x), button_text)
            row += 1

        stdscr.refresh()

    def _supports_interactive_curses(self) -> bool:
        """判断当前输出流是否支持交互式 curses。"""
        if not super()._supports_interactive_curses():
            return False
        return True

    def _footer_attr(self) -> int:
        """返回页脚统一使用的样式。"""
        return curses.A_DIM
