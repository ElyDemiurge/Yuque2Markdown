"""进度界面测试。"""

from io import StringIO
import pytest

from core_modules.export.models import ProgressSnapshot
from core_modules.export.progress import _BaseExportProgressUI, _display_width, _strip_ansi, _fit, ExportProgressUI


def test_display_width_ascii():
    assert _display_width("abc") == 3


def test_progress_entrypoint_keeps_public_api():
    assert issubclass(ExportProgressUI, _BaseExportProgressUI)


def test_display_width_chinese():
    assert _display_width("中文") == 4


def test_strip_ansi():
    text = "\033[31mred\033[0m"
    assert _strip_ansi(text) == "red"


def test_fit_short():
    assert _fit("hello", 10) == "hello"


def test_fit_long():
    result = _fit("hello world", 5)
    assert result.endswith("...")


class DummyStream(StringIO):
    def getwinsize(self):
        return (24, 100)


def test_progress_ui_update():
    stream = DummyStream()
    ui = ExportProgressUI(stream=stream)
    snapshot = ProgressSnapshot(total_docs=10, processed_docs=3, current_doc_title="Doc 1", current_stage="处理中")
    ui.update(snapshot)
    content = stream.getvalue()
    assert content is not None


def test_progress_ui_finish():
    stream = DummyStream()
    ui = ExportProgressUI(stream=stream)
    snapshot = ProgressSnapshot(total_docs=10, processed_docs=10, current_stage="已完成")
    ui.finish(snapshot)
    assert ui._finished is True


def test_progress_ui_finish_keeps_completion_lines_in_output():
    stream = DummyStream()
    ui = ExportProgressUI(stream=stream)
    ui.completion_lines = ["[导出结果]", "成功: 2 | 失败: 0"]
    snapshot = ProgressSnapshot(total_docs=2, processed_docs=2, current_stage="已完成")
    ui.finish(snapshot)
    content = stream.getvalue()
    assert "导出结果" in content
    assert "成功: 2 | 失败: 0" in content
    assert "返回" in content


def test_progress_ui_finish_uses_same_section_layout():
    stream = DummyStream()
    ui = ExportProgressUI(stream=stream)
    ui.completion_lines = ["[导出结果]", "成功: 2 | 失败: 0"]
    snapshot = ProgressSnapshot(total_docs=2, processed_docs=2, current_stage="已完成")
    ui.finish(snapshot)
    content = stream.getvalue()
    assert "── 导出结果 ──" in content
    assert "── 已完成 ── 0-0/0" in content
    assert "── 失败 ── 0-0/0" in content
    assert "── 等待队列 ── 0-0/0" in content
    assert "── 警告/错误 ── 警告 0 | 错误 0" in content
    assert "[导出结果]" not in content


def test_progress_ui_warning_history():
    stream = DummyStream()
    ui = ExportProgressUI(stream=stream)
    snapshot = ProgressSnapshot(latest_warning="warning 1")
    ui.update(snapshot)
    assert len(ui.history) == 1
    assert ui.history[0][0] == "WARN"


def test_progress_ui_appends_all_new_warnings():
    stream = DummyStream()
    ui = ExportProgressUI(stream=stream)
    snapshot = ProgressSnapshot(new_warnings=["warning 1", "warning 2"])
    ui.update(snapshot)
    assert [item[1] for item in ui.history] == ["warning 1", "warning 2"]


def test_progress_ui_keeps_duplicate_new_warnings_in_history():
    stream = DummyStream()
    ui = ExportProgressUI(stream=stream)
    snapshot = ProgressSnapshot(new_warnings=["warning 1", "warning 1"])
    ui.update(snapshot)
    assert [item[1] for item in ui.history] == ["warning 1", "warning 1"]


def test_progress_ui_error_history():
    stream = DummyStream()
    ui = ExportProgressUI(stream=stream)
    snapshot = ProgressSnapshot(latest_error="error 1")
    ui.update(snapshot)
    assert len(ui.history) == 1
    assert ui.history[0][0] == "ERROR"


def test_progress_ui_keeps_full_history_when_unbounded():
    stream = DummyStream()
    ui = ExportProgressUI(stream=stream)
    for index in range(8):
        ui.update(ProgressSnapshot(latest_warning=f"warning {index}"))
    assert len(ui.history) == 8
    lines = ui._plain_history_lines(80)
    visible, label = ui._slice_history_lines(lines, 3)
    assert len(visible) == 3
    assert label == "警告 8 | 错误 0"
    ui.history_scroll = 5
    visible, label = ui._slice_history_lines(lines, 3)
    assert visible[0].endswith("warning 5")
    assert label == "警告 8 | 错误 0"


def test_progress_ui_empty_section_uses_zero_range_label():
    ui = ExportProgressUI(stream=DummyStream())
    visible, label = ui._slice_section_lines("waiting_preview", ["  - 暂无"], 3)
    assert visible == ["  - 暂无", "", ""]
    assert label == "0-0/0"


def test_progress_ui_history_label_shows_warning_and_error_counts():
    ui = ExportProgressUI(stream=DummyStream())
    ui.update(ProgressSnapshot(new_warnings=["warning 1", "warning 1"]))
    ui.update(ProgressSnapshot(latest_error="error 1"))
    lines = ui._plain_history_lines(80)
    visible, label = ui._slice_display_lines("history", lines, 3)
    assert visible[0].endswith("warning 1")
    assert label == "警告 2 | 错误 1"


def test_progress_ui_empty_history_label_uses_zero_range_only():
    ui = ExportProgressUI(stream=DummyStream())
    lines = ui._plain_history_lines(80)
    visible, label = ui._slice_display_lines("history", lines, 3)
    assert visible == ["  - 暂无", "", ""]
    assert label == "警告 0 | 错误 0"


def test_progress_ui_finished_focus_can_move_to_return():
    ui = ExportProgressUI(stream=DummyStream())
    ui._finished = True
    snapshot = ProgressSnapshot(current_stage="已完成")
    for _ in range(4):
        ui._move_focus(snapshot, 1)
    assert ui.section_focus == 4
    assert ui._is_return_focused(snapshot) is True
    ui._scroll_active_section(snapshot, 1)
    assert ui.section_scrolls["history"] == 0


def test_stage_color():
    ui = ExportProgressUI(stream=DummyStream())
    assert ui._stage_color("已完成") == ui.GREEN
    assert ui._stage_color("导出失败") == ui.RED
    assert ui._stage_color("限流等待") == ui.YELLOW


def test_progress_ui_displays_live_current_doc_elapsed(monkeypatch):
    stream = DummyStream()
    ui = ExportProgressUI(stream=stream)
    monkeypatch.setattr("core_modules.export.progress.time.monotonic", lambda: 15.0)
    snapshot = ProgressSnapshot(
        current_doc_title="Doc 1",
        current_doc_started_monotonic=12.2,
        current_doc_resources=3,
    )
    parts = ui._collect_doc_stat_parts(snapshot)
    assert parts[0] == "耗时 2s"


def test_progress_ui_displays_total_export_elapsed(monkeypatch):
    stream = DummyStream()
    ui = ExportProgressUI(stream=stream)
    monkeypatch.setattr("core_modules.export.progress.time.monotonic", lambda: 21.5)
    snapshot = ProgressSnapshot(
        export_started_monotonic=10.0,
        completed_docs=2,
        skipped_docs=1,
        failed_docs=0,
        waiting_docs=3,
        warning_count=4,
    )
    assert "总耗时 11s" in ui._plain_stats_line(snapshot)


def test_windows_progress_ui_matches_unix_progress_bar_content():
    windows_ui_class = _import_windows_progress_ui_or_skip()
    ui = windows_ui_class(stream=DummyStream())

    line = ui._plain_progress_bar(ProgressSnapshot(total_docs=4, processed_docs=2), 40)

    assert _display_width(line) <= 40
    assert line.startswith("进度 ")
    assert "50.0%" in line
    assert "█" in line
    assert "░" in line


def test_windows_progress_ui_keeps_chinese_status_lines():
    windows_ui_class = _import_windows_progress_ui_or_skip()
    ui = windows_ui_class(stream=DummyStream())

    stats = ui._plain_stats_line(ProgressSnapshot(completed_docs=1, skipped_docs=2, failed_docs=3, warning_count=4))
    rate_limit = ui._plain_rate_limit_line(ProgressSnapshot())

    assert "完成 1" in stats
    assert "跳过 2" in stats
    assert "失败 3" in stats
    assert rate_limit == "  暂无响应头信息"


def test_windows_progress_ui_matches_unix_list_markers():
    windows_ui_class = _import_windows_progress_ui_or_skip()
    ui = windows_ui_class(stream=DummyStream())

    assert ui._plain_list(["文档 A"], "暂无", limit=None) == ["  • 文档 A"]


def test_windows_progress_draw_uses_safe_addstr_after_fit():
    try:
        from core_modules.export.progress_windows import _draw_progress_text, _fit_progress_text
    except ModuleNotFoundError as exc:
        if exc.name in {"_curses", "curses"}:
            pytest.skip("当前 Python 未安装 curses/windows-curses，跳过 Windows curses 渲染测试")
        raise

    class DummyScreen:
        def __init__(self):
            self.calls = []

        def getmaxyx(self):
            return 20, 80

        def move(self, row, col):
            self.calls.append(("move", row, col))

        def clrtoeol(self):
            self.calls.append(("clrtoeol",))

        def touchline(self, row, count):
            self.calls.append(("touchline", row, count))

        def addstr(self, row, col, text, attrs=0):
            self.calls.append(("addstr", row, col, text, attrs))

    screen = DummyScreen()

    _draw_progress_text(screen, 1, 2, "语雀导出", width=20, attrs=7)

    assert ("move", 1, 0) in screen.calls
    assert ("clrtoeol",) in screen.calls
    assert ("addstr", 1, 2, "语雀导出", 7) in screen.calls
    assert _fit_progress_text("中文abcdef", 8) == "中文a..."


def test_windows_progress_clear_marks_full_screen_dirty():
    try:
        from core_modules.export.progress_windows import _clear_progress_screen
    except ModuleNotFoundError as exc:
        if exc.name in {"_curses", "curses"}:
            pytest.skip("当前 Python 未安装 curses/windows-curses，跳过 Windows curses 渲染测试")
        raise

    class DummyScreen:
        def __init__(self):
            self.calls = []

        def getmaxyx(self):
            return 3, 10

        def clearok(self, flag):
            self.calls.append(("clearok", flag))

        def clear(self):
            self.calls.append(("clear",))

        def addstr(self, row, col, text, attrs=0):
            self.calls.append((row, col, text, attrs))

        def redrawwin(self):
            self.calls.append(("redrawwin",))

        def touchwin(self):
            self.calls.append(("touchwin",))

    screen = DummyScreen()

    _clear_progress_screen(screen, force=True)

    assert ("clearok", True) in screen.calls
    assert ("clear",) in screen.calls
    assert (0, 0, " " * 9, 0) in screen.calls
    assert (1, 0, " " * 9, 0) in screen.calls
    assert (2, 0, " " * 9, 0) in screen.calls
    assert ("redrawwin",) in screen.calls
    assert ("touchwin",) in screen.calls


def test_windows_progress_render_keeps_menu_txt_initial_screen_untruncated(monkeypatch):
    windows_ui_class = _import_windows_progress_ui_or_skip()
    import core_modules.export.progress_windows as progress_windows

    monkeypatch.setattr(progress_windows, "curses", DummyCurses)
    ui = windows_ui_class(stream=DummyStream())
    screen = DummyProgressScreen(height=50, width=210)

    ui._render_curses(screen, ProgressSnapshot(latest_event="初始化"))
    rendered = "\n".join(screen.rows)

    assert "语雀导出" in rendered
    assert "Ctrl+C 退出确认 | ←→ 切换区块 | ↑↓ 滚动区块 | PgUp/PgDn 快速滚动" in rendered
    assert "[0/0]   0.0%" in rendered
    assert "── 统计 ──" in rendered
    assert "完成 0 | 跳过 0 | 失败 0 | 等待 0 | 警告 0" in rendered
    assert "  暂无响应头信息" in rendered
    assert "── 正在进行 ──" in rendered
    assert "── 已完成 ── 0-0/0" in rendered
    assert "── 失败 ── 0-0/0" in rendered
    assert "── 等待队列 ── 0-0/0" in rendered
    assert "── 警告/错误 ── 警告 0 | 错误 0" in rendered
    assert "事件: 初始化" in rendered


def test_windows_progress_render_keeps_menu_txt_running_screen_untruncated(monkeypatch):
    windows_ui_class = _import_windows_progress_ui_or_skip()
    import core_modules.export.progress_windows as progress_windows

    monkeypatch.setattr(progress_windows, "curses", DummyCurses)
    ui = windows_ui_class(stream=DummyStream())
    screen = DummyProgressScreen(height=50, width=210)
    snapshot = ProgressSnapshot(
        total_docs=224,
        processed_docs=12,
        skipped_docs=12,
        waiting_docs=212,
        current_stage="下载图片并执行附件本地化",
        current_doc_title="《IoT从入门到入土》(5)--模拟固件下的patch与hook（1）",
        current_doc_elapsed_ms=3000,
        current_doc_resources=123,
        active_tasks=[
            "处理资源: 《IoT从入门到入土》(5)--模拟固件下的patch与hook（1）",
            "改写内部链接: 《IoT从入门到入土》(5)--模拟固件下的patch与hook（1）",
        ],
        recent_completed=[
            "跳过 SQL注入入门（3）--CTF",
            "跳过 SQL注入入门（2）--SQLi-labs-Less-2（GET-）",
            "跳过 SQL注入入门（1）--SQLi-labs-Less-1（GET-）",
        ],
        waiting_preview=[
            "《IoT从入门到入土》(4)--Cisco RV",
            "《IoT从入门到入土》(3)--BooFuzz的简单使用",
            "《IoT从入门到入土》(2-2)--某摄像头存在通信问题",
        ],
        latest_event="正在处理 《IoT从入门到入土》(5)--模拟固件下的patch与hook（1） 的资源",
        details={"log_path": r"output\公开知识库\export.log"},
    )

    ui._render_curses(screen, snapshot)
    rendered = "\n".join(screen.rows)

    assert "语雀导出" in rendered
    assert "Ctrl+C 退出确认 | ←→ 切换区块 | ↑↓ 滚动区块 | PgUp/PgDn 快速滚动" in rendered
    assert "[12/224]   5.4%" in rendered
    assert "下载图片并执行附件本地化" in rendered
    assert "  暂无响应头信息" in rendered
    assert "── 正在进行 ──" in rendered
    assert r"日志: output\公开知识库\export.log" in rendered


def _import_windows_progress_ui_or_skip():
    try:
        from core_modules.export.progress_windows import ExportProgressUI as WindowsExportProgressUI
    except ModuleNotFoundError as exc:
        if exc.name in {"_curses", "curses"}:
            pytest.skip("当前 Python 未安装 curses/windows-curses，跳过 Windows curses 渲染测试")
        raise
    return WindowsExportProgressUI


class DummyProgressScreen:
    def __init__(self, *, height: int, width: int) -> None:
        self.height = height
        self.width = width
        self.rows = [" " * width for _ in range(height)]
        self.cursor = (0, 0)
        self.calls = []

    def getmaxyx(self):
        return self.height, self.width

    def clearok(self, flag):
        self.calls.append(("clearok", flag))

    def clear(self):
        self.rows = [" " * self.width for _ in range(self.height)]
        self.calls.append(("clear",))

    def addstr(self, row, col, text, attrs=0):
        self._write(row, col, text)
        self.calls.append(("addstr", row, col, text, attrs))

    def addnstr(self, row, col, text, count, attrs=0):
        self._write(row, col, text[:count])
        self.calls.append(("addnstr", row, col, text, count, attrs))

    def move(self, row, col):
        self.cursor = (row, col)
        self.calls.append(("move", row, col))

    def clrtoeol(self):
        row, col = self.cursor
        if 0 <= row < self.height:
            self.rows[row] = self.rows[row][:col] + (" " * max(0, self.width - col))
        self.calls.append(("clrtoeol",))

    def touchline(self, row, count):
        self.calls.append(("touchline", row, count))

    def redrawwin(self):
        self.calls.append(("redrawwin",))

    def touchwin(self):
        self.calls.append(("touchwin",))

    def refresh(self):
        self.calls.append(("refresh",))

    def _write(self, row: int, col: int, text: str) -> None:
        if not (0 <= row < self.height) or col >= self.width:
            return
        col = max(0, col)
        available = max(0, self.width - col)
        chunk = text[:available]
        self.rows[row] = self.rows[row][:col] + chunk + self.rows[row][col + len(chunk):]


class DummyCurses:
    class error(Exception):
        pass

    A_NORMAL = 0
    A_DIM = 1
    A_BOLD = 2
    A_REVERSE = 4
    COLOR_CYAN = 6
    COLOR_BLUE = 4
    COLOR_GREEN = 2
    COLOR_YELLOW = 3
    COLOR_RED = 1
    COLOR_MAGENTA = 5

    @staticmethod
    def has_colors():
        return False
