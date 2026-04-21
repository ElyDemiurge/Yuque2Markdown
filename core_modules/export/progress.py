from __future__ import annotations

import curses
import os
import threading
import time
import unicodedata
from dataclasses import replace
from io import StringIO
from typing import Callable, TypeVar

from core_modules.export.models import ProgressSnapshot
from core_modules.console.menu import _is_screen_too_small, _render_screen_too_small

T = TypeVar("T")


# Unicode 全角字符宽度（用于计算显示宽度）
def _char_display_width(char: str) -> int:
    return 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1


def _display_width(text: str) -> int:
    width = 0
    for char in text:
        width += _char_display_width(char)
    return width



def _strip_ansi(text: str) -> str:
    result: list[str] = []
    i = 0
    while i < len(text):
        if text[i] == "\033":
            while i < len(text) and text[i] != "m":
                i += 1
            i += 1
            continue
        result.append(text[i])
        i += 1
    return "".join(result)



def _fit(text: str, width: int) -> str:
    visible = _strip_ansi(text)
    vis_len = _display_width(visible)
    if vis_len <= width:
        return text
    if width <= 3:
        return visible[:width]
    current = 0
    result: list[str] = []
    for char in visible:
        char_width = _char_display_width(char)
        if current + char_width > width - 3:
            break
        result.append(char)
        current += char_width
    return "".join(result) + "..."


class ExportProgressUI:
    """导出进度 UI，支持实时更新、警告滚动查看与中断确认。"""

    HISTORY_VISIBLE_ROWS = 3

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    CYAN = "\033[36m"
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    RED = "\033[31m"
    MAGENTA = "\033[35m"

    def __init__(self, *, stream=None, history_size: int | None = None) -> None:
        self.stream = stream or __import__("sys").stdout
        self.history_limit = history_size
        self.history: list[tuple[str, str]] = []
        self.last_rendered_lines = 0
        self._finished = False
        self.use_color = self._supports_color()
        self.latest_snapshot = ProgressSnapshot()
        self.completion_lines: list[str] = []
        self.history_scroll = 0
        self.section_focus = 0
        self.section_scrolls = {
            "recent_completed": 0,
            "recent_failed": 0,
            "waiting_preview": 0,
            "history": 0,
        }
        self._last_warning: str | None = None
        self._last_error: str | None = None

    def update(self, snapshot: ProgressSnapshot) -> None:
        self.latest_snapshot = replace(snapshot)
        self._append_history(snapshot)
        if not self._supports_interactive_curses():
            self._render_ansi(self.latest_snapshot)

    def finish(self, snapshot: ProgressSnapshot) -> None:
        self._finished = True
        final_snapshot = replace(snapshot, current_stage="已完成")
        self.latest_snapshot = final_snapshot
        self._append_history(final_snapshot)
        if not self._supports_interactive_curses():
            self._render_ansi(final_snapshot)
            self.stream.write("\n")
            self.stream.flush()

    def run(
        self,
        worker: Callable[[], T],
        *,
        on_interrupt: Callable[[], bool] | None = None,
        on_complete: Callable[[T], list[str]] | None = None,
    ) -> T:
        """在独立线程中执行导出任务，并用 curses 展示可交互进度界面。"""
        if not self._supports_interactive_curses():
            value = worker()
            if on_complete is not None:
                self.completion_lines = list(on_complete(value))
            return value

        result: dict[str, object] = {"value": None, "error": None}

        def _target() -> None:
            try:
                result["value"] = worker()
            except Exception as exc:  # noqa: BLE001
                result["error"] = exc

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()

        while True:
            try:
                curses.wrapper(lambda stdscr: self._run_curses(stdscr, thread, result, on_complete))
                break
            except KeyboardInterrupt:
                if on_interrupt is not None and not on_interrupt():
                    continue
                while thread.is_alive():
                    time.sleep(0.05)
                raise

        if result["error"] is not None:
            raise result["error"]  # type: ignore[misc]
        return result["value"]  # type: ignore[return-value]

    def _append_history(self, snapshot: ProgressSnapshot) -> None:
        if snapshot.new_warnings:
            for warning in snapshot.new_warnings:
                if warning != self._last_warning:
                    self.history.append(("WARN", warning))
                    self._last_warning = warning
        elif snapshot.latest_warning and snapshot.latest_warning != self._last_warning:
            self.history.append(("WARN", snapshot.latest_warning))
            self._last_warning = snapshot.latest_warning
        if snapshot.latest_error and snapshot.latest_error != self._last_error:
            self.history.append(("ERROR", snapshot.latest_error))
            self._last_error = snapshot.latest_error
        if self.history_limit is not None and len(self.history) > self.history_limit:
            self.history = self.history[-self.history_limit :]
        self._clamp_history_scroll()

    def _run_curses(self, stdscr, thread: threading.Thread, result: dict[str, object], on_complete) -> None:
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
                self.completion_lines = list(on_complete(result["value"]))
                completion_built = True
            self._render_curses(stdscr, snapshot)
            if not thread.is_alive():
                stdscr.timeout(-1)
                key = stdscr.getch()
                if key == curses.KEY_LEFT:
                    self.section_focus = max(0, self.section_focus - 1)
                    continue
                if key == curses.KEY_RIGHT:
                    self.section_focus = min(3, self.section_focus + 1)
                    continue
                if key == curses.KEY_UP:
                    self._scroll_active_section(-1)
                    continue
                if key == curses.KEY_DOWN:
                    self._scroll_active_section(1)
                    continue
                if key == curses.KEY_PPAGE:
                    self._scroll_active_section(-self.HISTORY_VISIBLE_ROWS)
                    continue
                if key == curses.KEY_NPAGE:
                    self._scroll_active_section(self.HISTORY_VISIBLE_ROWS)
                    continue
                break
            key = stdscr.getch()
            if key == -1:
                continue
            if key == 3:
                raise KeyboardInterrupt
            if key == curses.KEY_LEFT:
                self.section_focus = max(0, self.section_focus - 1)
            elif key == curses.KEY_RIGHT:
                self.section_focus = min(3, self.section_focus + 1)
            elif key == curses.KEY_UP:
                self._scroll_active_section(-1)
            elif key == curses.KEY_DOWN:
                self._scroll_active_section(1)
            elif key == curses.KEY_PPAGE:
                self._scroll_active_section(-self.HISTORY_VISIBLE_ROWS)
            elif key == curses.KEY_NPAGE:
                self._scroll_active_section(self.HISTORY_VISIBLE_ROWS)

    def _render_ansi(self, snapshot: ProgressSnapshot) -> None:
        _, raw_width = self.stream.getwinsize() if hasattr(self.stream, "getwinsize") else (None, 100)
        width = max(72, raw_width or 100)
        content_width = min(128, max(60, width - 4))
        left = max(0, (width - content_width) // 2)
        title_text = "语雀导出"
        title_x = max(0, (width - _display_width(title_text)) // 2)
        title = self._colorize(title_text, self.BOLD, self.CYAN)
        sep = self._colorize("─" * content_width, self._dim_gray())

        lines: list[tuple[int, str]] = [
            (title_x, title),
            (left, sep),
            (left, self._build_progress_bar(snapshot, content_width)),
            (left, self._section_value("阶段", snapshot.current_stage, self._stage_color(snapshot.current_stage), content_width)),
            (left, self._section_value("当前", snapshot.current_doc_title or "—", self.BLUE, content_width)),
        ]
        doc_stats = self._build_current_doc_stats(snapshot)
        if doc_stats:
            lines.append((left, doc_stats))
        lines.extend(
            [
                (left, sep),
                (left, self._section_header("统计")),
                (left, self._build_stats_line(snapshot)),
            ]
        )
        if self._finished and self.completion_lines:
            lines.append((left, sep))
            lines.append((left, self._section_header("导出结果")))
            for line in self.completion_lines:
                lines.append((left, _fit(line, content_width)))
        lines.extend(
            [
                (left, sep),
                (left, self._section_header("警告/异常")),
            ]
        )
        for line in self._format_history_ansi(content_width):
            lines.append((left, line))
        footer_lines = self._build_footer_lines(snapshot)
        if footer_lines:
            lines.append((left, sep))
            for text, _attr in footer_lines:
                lines.append((left, _fit(text, content_width)))
        lines.append((left, sep))
        if self._finished:
            button_text = self._build_return_button()
            button_x = max(0, (width - _display_width(_strip_ansi(button_text))) // 2)
            lines.append((button_x, button_text))
            lines.append((left, sep))

        total_lines = len(lines)
        if self.last_rendered_lines:
            self.stream.write(f"\x1b[{self.last_rendered_lines}F")
        for index, (x, text) in enumerate(lines):
            self.stream.write("\r\x1b[2K")
            self.stream.write(" " * x)
            self.stream.write(_fit(text, content_width))
            if index < total_lines - 1:
                self.stream.write("\n")
        extra_lines = self.last_rendered_lines - total_lines
        for _ in range(max(0, extra_lines)):
            self.stream.write("\n\r\x1b[2K")
        if extra_lines > 0:
            self.stream.write(f"\x1b[{extra_lines}F")
        self.stream.flush()
        self.last_rendered_lines = total_lines

    def _render_curses(self, stdscr, snapshot: ProgressSnapshot) -> None:
        stdscr.clear()
        height, width = stdscr.getmaxyx()
        help_lines = (
            ["任意键返回 | ←→ 切换区块 | ↑↓ 滚动区块 | PgUp/PgDn 快速滚动"]
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
        scroll_sections: list[tuple[str, str, list[str], str]] = []
        if self._finished and self.completion_lines:
            fixed_lines.extend(
                [
                    ("─" * content_width, self._curses_attr(curses, "divider")),
                    ("── 导出结果 ──", self._curses_attr(curses, "section")),
                ]
            )
            fixed_lines.extend((line, self._curses_attr(curses, "active")) for line in self.completion_lines)
        else:
            fixed_lines.extend(
                [
                    ("─" * content_width, self._curses_attr(curses, "divider")),
                    ("── 正在进行 ──", self._curses_attr(curses, "section")),
                ]
            )
            fixed_lines.extend((line, self._curses_attr(curses, "active")) for line in self._plain_list(snapshot.active_tasks, "暂无", limit=3))
            waiting_titles = snapshot.details.get("_waiting_titles")
            if not isinstance(waiting_titles, list):
                waiting_titles = list(snapshot.waiting_preview)
            scroll_sections.extend(
                [
                    ("recent_completed", "已完成", self._plain_list(snapshot.recent_completed, "暂无", limit=None), "completed"),
                    ("recent_failed", "失败", self._plain_list(snapshot.recent_failed, "暂无", limit=None), "failed"),
                    ("waiting_preview", "等待队列", self._plain_list(waiting_titles, "暂无", limit=None), "waiting"),
                ]
            )
        scroll_sections.append(("history", "警告/异常", self._plain_history_lines(content_width), "warning"))

        footer_lines = self._build_footer_lines(snapshot)
        footer_block_rows = len(footer_lines)
        if footer_lines:
            footer_block_rows += 1
        if self._finished:
            footer_block_rows += 1
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
            visible_lines, scroll_label = self._slice_section_lines(section_key, section_lines, available_section_rows)
            display_label = scroll_label
            if section_key == "history" and scroll_label.startswith("警告 "):
                display_label = scroll_label[len("警告 "):]
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
            button_text = self._build_return_button(curses)
            button_x = max(0, (width - _display_width(" 返回 ")) // 2)
            stdscr.addnstr(row, button_x, " 返回 ", min(content_width, width - button_x), button_text)
            row += 1

        stdscr.refresh()

    def _build_progress_bar(self, snapshot: ProgressSnapshot, width: int) -> str:
        total = max(snapshot.total_docs, 1)
        processed = min(snapshot.processed_docs, total)
        ratio = processed / total
        label = f"[{processed}/{snapshot.total_docs}] {ratio * 100:5.1f}%"
        bar_width = max(10, width - _display_width(label) - 4)
        filled = min(bar_width, int(bar_width * ratio))
        prefix = "进度 "
        filled_bar = self._colorize("█" * filled, self.GREEN)
        empty_bar = self._colorize("░" * (bar_width - filled), self._dim_gray())
        return f"{prefix}{filled_bar}{empty_bar} {label}"

    def _plain_progress_bar(self, snapshot: ProgressSnapshot, width: int) -> str:
        total = max(snapshot.total_docs, 1)
        processed = min(snapshot.processed_docs, total)
        ratio = processed / total
        label = f"[{processed}/{snapshot.total_docs}] {ratio * 100:5.1f}%"
        bar_width = max(10, width - _display_width(label) - 4)
        filled = min(bar_width, int(bar_width * ratio))
        return f"进度 {'█' * filled}{'░' * (bar_width - filled)} {label}"

    def _build_current_doc_stats(self, snapshot: ProgressSnapshot) -> str:
        parts = self._collect_doc_stat_parts(snapshot)
        if not parts:
            return ""
        return "  " + " │ ".join(parts)

    def _plain_current_doc_stats(self, snapshot: ProgressSnapshot) -> str:
        parts = self._collect_doc_stat_parts(snapshot)
        if not parts:
            return ""
        return "  " + " | ".join(_strip_ansi(part) for part in parts)

    def _collect_doc_stat_parts(self, snapshot: ProgressSnapshot) -> list[str]:
        if not snapshot.current_doc_title:
            return []
        parts: list[str] = []
        current_doc_elapsed_ms = self._current_doc_elapsed_ms(snapshot)
        if current_doc_elapsed_ms > 0:
            parts.append(f"耗时 {current_doc_elapsed_ms // 1000}s")
        if snapshot.current_doc_warnings > 0:
            parts.append(self._colorize(f"[!] {snapshot.current_doc_warnings} 警告", self.YELLOW))
        if snapshot.current_doc_resources > 0:
            parts.append(f"资源 {snapshot.current_doc_resources}")
        if snapshot.current_doc_downloaded > 0:
            parts.append(f"已下载 {snapshot.current_doc_downloaded}")
        return parts

    def _build_stats_line(self, snapshot: ProgressSnapshot) -> str:
        items = [
            ("完成", snapshot.completed_docs, self.GREEN),
            ("跳过", snapshot.skipped_docs, self._dim_gray()),
            ("失败", snapshot.failed_docs, self.RED),
            ("等待", snapshot.waiting_docs, self.MAGENTA),
            ("警告", snapshot.warning_count, self.YELLOW),
        ]
        parts = [self._colorize(f"{label} {count}", color if count > 0 else self._dim_gray()) for label, count, color in items]
        export_elapsed_ms = self._export_elapsed_ms(snapshot)
        if export_elapsed_ms > 0:
            parts.append(self._colorize(f"总耗时 {export_elapsed_ms // 1000}s", self.CYAN))
        return "  " + " │ ".join(parts)

    def _plain_stats_line(self, snapshot: ProgressSnapshot) -> str:
        line = (
            f"  完成 {snapshot.completed_docs} | 跳过 {snapshot.skipped_docs} | "
            f"失败 {snapshot.failed_docs} | 等待 {snapshot.waiting_docs} | 警告 {snapshot.warning_count}"
        )
        export_elapsed_ms = self._export_elapsed_ms(snapshot)
        if export_elapsed_ms > 0:
            line += f" | 总耗时 {export_elapsed_ms // 1000}s"
        return line

    def _current_doc_elapsed_ms(self, snapshot: ProgressSnapshot) -> int:
        if snapshot.current_doc_started_monotonic > 0 and snapshot.current_doc_title:
            return max(0, int((time.monotonic() - snapshot.current_doc_started_monotonic) * 1000))
        return max(0, snapshot.current_doc_elapsed_ms)

    def _export_elapsed_ms(self, snapshot: ProgressSnapshot) -> int:
        if snapshot.export_started_monotonic > 0:
            return max(0, int((time.monotonic() - snapshot.export_started_monotonic) * 1000))
        return 0

    def _plain_rate_limit_line(self, snapshot: ProgressSnapshot) -> str:
        if snapshot.rate_limit_limit is None and snapshot.rate_limit_remaining is None and not snapshot.rate_limit_reset:
            return "  暂无响应头信息"
        parts = [
            f"Limit {snapshot.rate_limit_limit if snapshot.rate_limit_limit is not None else '-'}",
            f"Remaining {snapshot.rate_limit_remaining if snapshot.rate_limit_remaining is not None else '-'}",
        ]
        if snapshot.rate_limit_reset:
            parts.append(f"Reset {snapshot.rate_limit_reset}")
        return "  " + " | ".join(parts)

    def _plain_list(self, items: list[str], empty_text: str, *, limit: int | None) -> list[str]:
        if not items:
            return [f"  - {empty_text}"]
        source = items if limit is None else items[:limit]
        return [f"  • {item}" for item in source]

    def _format_history_ansi(self, width: int) -> list[str]:
        if not self.history:
            return ["  " + self._colorize("- 暂无", self._dim_gray())]
        lines: list[str] = []
        for level, message in self.history[-self.HISTORY_VISIBLE_ROWS :]:
            color = self.YELLOW if level == "WARN" else self.RED
            prefix = "[!]" if level == "WARN" else "[×]"
            lines.append(f"  {self._colorize(prefix, color)} {_fit(message, width - 6)}")
        return lines

    def _plain_history_lines(self, width: int) -> list[str]:
        if not self.history:
            return ["  - 暂无"]
        lines: list[str] = []
        for level, message in self.history:
            prefix = "[!]" if level == "WARN" else "[x]"
            lines.append(f"  {prefix} {_fit(message, width - 6)}")
        return lines

    def _slice_history_lines(self, lines: list[str], visible_rows: int) -> tuple[list[str], str]:
        visible, label = self._slice_section_lines("history", lines, visible_rows)
        return visible, f"警告 {label}"

    def _build_footer_lines(self, snapshot: ProgressSnapshot) -> list[tuple[str, int]]:
        lines: list[tuple[str, int]] = []
        latest = snapshot.latest_event or "导出进行中"
        lines.append((f"事件: {latest}", self._footer_attr("event")))
        log_path = str(snapshot.details.get("log_path") or "")
        if log_path:
            lines.append((f"日志: {log_path}", self._footer_attr("log")))
        return lines

    def _build_return_button(self, curses_module=None):
        if curses_module is not None:
            return curses_module.A_REVERSE | curses_module.A_BOLD
        return self._colorize(" 返回 ", self.BOLD, self.CYAN)

    def _clamp_history_scroll(self) -> None:
        self.section_scrolls["history"] = max(0, self.section_scrolls.get("history", 0))
        self.history_scroll = self.section_scrolls["history"]

    def _scroll_active_section(self, delta: int) -> None:
        section_key = ["recent_completed", "recent_failed", "waiting_preview", "history"][self.section_focus]
        self.section_scrolls[section_key] = max(0, self.section_scrolls.get(section_key, 0) + delta)
        if section_key == "history":
            self.history_scroll = self.section_scrolls[section_key]

    def _slice_section_lines(self, section_key: str, lines: list[str], visible_rows: int) -> tuple[list[str], str]:
        if not lines:
            return [f"  - 暂无"] + [""] * max(0, visible_rows - 1), "0/0"
        if section_key == "history":
            self.section_scrolls["history"] = self.history_scroll
        max_scroll = max(0, len(lines) - visible_rows)
        current_scroll = min(self.section_scrolls.get(section_key, 0), max_scroll)
        self.section_scrolls[section_key] = current_scroll
        if section_key == "history":
            self.history_scroll = current_scroll
        start = current_scroll
        end = min(len(lines), start + visible_rows)
        visible = list(lines[start:end])
        if len(visible) < visible_rows:
            visible.extend([""] * (visible_rows - len(visible)))
        label_end = min(start + visible_rows, len(lines))
        return visible, f"{start + 1}-{label_end}/{len(lines)}"

    def _section_header(self, text: str) -> str:
        return self._colorize(f"── {text} ──", self.BOLD, self.CYAN)

    def _section_value(self, label: str, value: str, color: str, width: int) -> str:
        label_str = f"{label}: "
        value_str = _fit(value, width - _display_width(label_str) - 2)
        return label_str + self._colorize(value_str, color)

    def _stage_color(self, stage: str) -> str:
        if "完成" in stage or "成功" in stage:
            return self.GREEN
        if "失败" in stage or "错误" in stage:
            return self.RED
        if "跳过" in stage:
            return self._dim_gray()
        if "限流" in stage:
            return self.YELLOW
        return self.CYAN

    def _status_attr(self, stage: str, curses_module) -> int:
        if "完成" in stage or "成功" in stage:
            return self._curses_attr(curses_module, "completed")
        if "失败" in stage or "错误" in stage:
            return self._curses_attr(curses_module, "error")
        if "限流" in stage:
            return self._curses_attr(curses_module, "warning")
        return self._curses_attr(curses_module, "stage")

    def _footer_attr(self, kind: str) -> int:
        return curses.A_DIM

    def _init_curses_colors(self, curses_module) -> None:
        if not curses_module.has_colors():
            return
        try:
            curses_module.start_color()
            curses_module.use_default_colors()
            curses_module.init_pair(11, curses_module.COLOR_CYAN, -1)
            curses_module.init_pair(12, curses_module.COLOR_BLUE, -1)
            curses_module.init_pair(13, curses_module.COLOR_GREEN, -1)
            curses_module.init_pair(14, curses_module.COLOR_YELLOW, -1)
            curses_module.init_pair(15, curses_module.COLOR_RED, -1)
            curses_module.init_pair(16, curses_module.COLOR_MAGENTA, -1)
        except curses_module.error:
            return

    def _curses_attr(self, curses_module, role: str) -> int:
        base_map = {
            "title": curses_module.A_BOLD,
            "help": curses_module.A_DIM,
            "divider": curses_module.A_DIM,
            "progress": curses_module.A_BOLD,
            "current_doc": curses_module.A_NORMAL,
            "section": curses_module.A_BOLD,
            "stats": curses_module.A_NORMAL,
            "rate_limit": curses_module.A_DIM,
            "active": curses_module.A_NORMAL,
            "completed": curses_module.A_BOLD,
            "failed": curses_module.A_BOLD,
            "waiting": curses_module.A_NORMAL,
            "warning": curses_module.A_BOLD,
            "error": curses_module.A_BOLD,
            "stage": curses_module.A_BOLD,
        }
        attr = base_map.get(role, curses_module.A_NORMAL)
        if not curses_module.has_colors():
            return attr
        pair_map = {
            "title": 11,
            "help": 12,
            "progress": 13,
            "section": 11,
            "rate_limit": 12,
            "active": 12,
            "completed": 13,
            "failed": 15,
            "waiting": 16,
            "warning": 14,
            "error": 15,
            "stage": 11,
            "current_doc": 12,
            "stats": 11,
        }
        pair_id = pair_map.get(role)
        if pair_id is None:
            return attr
        try:
            return attr | curses_module.color_pair(pair_id)
        except curses_module.error:
            return attr

    def _supports_interactive_curses(self) -> bool:
        if isinstance(self.stream, StringIO):
            return False
        if not hasattr(self.stream, "isatty") or not self.stream.isatty():
            return False
        return os.getenv("TERM") not in {None, "", "dumb"}

    def _dim_gray(self) -> str:
        return self.DIM

    def _supports_color(self) -> bool:
        if os.getenv("NO_COLOR"):
            return False
        return hasattr(self.stream, "isatty") and self.stream.isatty()

    def _colorize(self, text: str, *styles: str) -> str:
        if not self.use_color or not styles:
            return text
        return "".join(styles) + text + self.RESET
