from __future__ import annotations

import curses
import os
import threading
import unicodedata
from dataclasses import replace
from io import StringIO
from typing import Callable, TypeVar

from core_modules.export.models import ProgressSnapshot

T = TypeVar("T")


# Unicode 全角字符宽度（用于计算显示宽度）
def _display_width(text: str) -> int:
    width = 0
    for char in text:
        width += 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
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
        char_width = 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
        if current + char_width > width - 3:
            break
        result.append(char)
        current += char_width
    return "".join(result) + "..."


class ExportProgressUI:
    """导出进度 UI，支持实时更新、警告滚动查看与中断确认。"""

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
        self.history_scroll = 0
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

    def run(self, worker: Callable[[], T], *, on_interrupt: Callable[[], bool] | None = None) -> T:
        """在独立线程中执行导出任务，并用 curses 展示可交互进度界面。"""
        if not self._supports_interactive_curses():
            return worker()

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
                curses.wrapper(lambda stdscr: self._run_curses(stdscr, thread))
                break
            except KeyboardInterrupt:
                if on_interrupt is not None and not on_interrupt():
                    continue
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

    def _run_curses(self, stdscr, thread: threading.Thread) -> None:
        curses.curs_set(0)
        self._init_curses_colors(curses)
        stdscr.timeout(150)
        while True:
            snapshot = self.latest_snapshot
            if not thread.is_alive() and not self._finished:
                self._finished = True
                snapshot = replace(snapshot, current_stage="已完成")
                self.latest_snapshot = snapshot
            self._render_curses(stdscr, snapshot)
            if not thread.is_alive():
                break
            key = stdscr.getch()
            if key == -1:
                continue
            if key == 3:
                raise KeyboardInterrupt
            if key == curses.KEY_UP:
                self.history_scroll = max(0, self.history_scroll - 1)
            elif key == curses.KEY_DOWN:
                self.history_scroll += 1
            elif key == curses.KEY_PPAGE:
                self.history_scroll = max(0, self.history_scroll - 5)
            elif key == curses.KEY_NPAGE:
                self.history_scroll += 5
            self._clamp_history_scroll()

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
                (left, sep),
                (left, self._section_header("警告")),
            ]
        )
        for line in self._format_history_ansi(content_width):
            lines.append((left, line))
        log_path = str(snapshot.details.get("log_path") or "")
        if log_path:
            lines.append((left, sep))
            lines.append((left, self._section_value("日志", log_path, self.CYAN, content_width)))
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
        help_lines = ["Ctrl+C 退出确认 | ↑↓ 滚动警告 | PgUp/PgDn 快速滚动"]
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
        fixed_lines.extend(
            [
                ("─" * content_width, self._curses_attr(curses, "divider")),
                ("── 正在进行 ──", self._curses_attr(curses, "section")),
            ]
        )
        fixed_lines.extend((line, self._curses_attr(curses, "active")) for line in self._plain_list(snapshot.active_tasks, "无活动任务", limit=3))
        fixed_lines.extend(
            [
                ("─" * content_width, self._curses_attr(curses, "divider")),
                ("── 最近完成 ──", self._curses_attr(curses, "section")),
            ]
        )
        fixed_lines.extend((line, self._curses_attr(curses, "completed")) for line in self._plain_list(snapshot.recent_completed, "暂无完成记录", limit=3))
        fixed_lines.extend(
            [
                ("─" * content_width, self._curses_attr(curses, "divider")),
                ("── 最近失败 ──", self._curses_attr(curses, "section")),
            ]
        )
        fixed_lines.extend((line, self._curses_attr(curses, "failed")) for line in self._plain_list(snapshot.recent_failed, "暂无失败记录", limit=3))
        fixed_lines.extend(
            [
                ("─" * content_width, self._curses_attr(curses, "divider")),
                ("── 等待队列 ──", self._curses_attr(curses, "section")),
            ]
        )
        fixed_lines.extend((line, self._curses_attr(curses, "waiting")) for line in self._plain_list(snapshot.waiting_preview, "队列为空", limit=3))
        fixed_lines.extend(
            [
                ("─" * content_width, self._curses_attr(curses, "divider")),
                ("── 警告 ──", self._curses_attr(curses, "section")),
            ]
        )

        footer_lines = self._build_footer_lines(snapshot)
        reserved_footer = len(footer_lines) + 1
        available_warning_rows = max(3, height - row - len(fixed_lines) - reserved_footer)

        for text, attr in fixed_lines:
            if row >= height:
                break
            stdscr.addnstr(row, left, _fit(text, content_width), content_width, attr)
            row += 1

        history_lines = self._plain_history_lines(content_width)
        visible_history, scroll_label = self._slice_history_lines(history_lines, available_warning_rows)
        for line in visible_history:
            if row >= height:
                break
            history_attr = self._curses_attr(curses, "warning") if "[!]" in line else self._curses_attr(curses, "error")
            stdscr.addnstr(row, left, _fit(line, content_width), content_width, history_attr)
            row += 1
        if row < height:
            stdscr.addnstr(row, left, _fit(scroll_label, content_width), content_width, self._curses_attr(curses, "help"))
            row += 1

        if row < height:
            stdscr.addnstr(row, left, "─" * max(0, content_width), content_width, self._curses_attr(curses, "divider"))
            row += 1

        for text, attr in footer_lines:
            if row >= height:
                break
            stdscr.addnstr(row, left, _fit(text, content_width), content_width, attr)
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
        if snapshot.current_doc_elapsed_ms > 0:
            parts.append(f"耗时 {snapshot.current_doc_elapsed_ms / 1000:.1f}s")
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
        return "  " + " │ ".join(parts)

    def _plain_stats_line(self, snapshot: ProgressSnapshot) -> str:
        return (
            f"  完成 {snapshot.completed_docs} | 跳过 {snapshot.skipped_docs} | "
            f"失败 {snapshot.failed_docs} | 等待 {snapshot.waiting_docs} | 警告 {snapshot.warning_count}"
        )

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

    def _plain_list(self, items: list[str], empty_text: str, *, limit: int) -> list[str]:
        if not items:
            return [f"  - {empty_text}"]
        return [f"  • {item}" for item in items[:limit]]

    def _format_history_ansi(self, width: int) -> list[str]:
        if not self.history:
            return ["  " + self._colorize("─ 暂无警告或异常", self._dim_gray())]
        lines: list[str] = []
        for level, message in self.history[-6:]:
            color = self.YELLOW if level == "WARN" else self.RED
            prefix = "[!]" if level == "WARN" else "[×]"
            lines.append(f"  {self._colorize(prefix, color)} {_fit(message, width - 6)}")
        return lines

    def _plain_history_lines(self, width: int) -> list[str]:
        if not self.history:
            return ["  - 暂无警告或异常"]
        lines: list[str] = []
        for level, message in self.history:
            prefix = "[!]" if level == "WARN" else "[x]"
            lines.append(f"  {prefix} {_fit(message, width - 6)}")
        return lines

    def _slice_history_lines(self, lines: list[str], visible_rows: int) -> tuple[list[str], str]:
        if not lines:
            return ["  - 暂无警告或异常"], "警告 0/0"
        max_scroll = max(0, len(lines) - visible_rows)
        self.history_scroll = min(self.history_scroll, max_scroll)
        start = self.history_scroll
        end = min(len(lines), start + visible_rows)
        return lines[start:end], f"警告 {start + 1}-{end}/{len(lines)}"

    def _build_footer_lines(self, snapshot: ProgressSnapshot) -> list[tuple[str, int]]:
        lines: list[tuple[str, int]] = []
        latest = snapshot.latest_event or "导出进行中"
        lines.append((f"事件: {latest}", self._footer_attr("event")))
        log_path = str(snapshot.details.get("log_path") or "")
        if log_path:
            lines.append((f"日志: {log_path}", self._footer_attr("log")))
        return lines

    def _clamp_history_scroll(self) -> None:
        max_scroll = max(0, len(self.history) - 1)
        self.history_scroll = max(0, min(self.history_scroll, max_scroll))

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
