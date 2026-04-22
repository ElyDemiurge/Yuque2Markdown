"""进度界面测试。"""
import sys
sys.path.insert(0, ".")

from io import StringIO
from core_modules.export.models import ProgressSnapshot
from core_modules.export.progress import _display_width, _strip_ansi, _fit, ExportProgressUI


def test_display_width_ascii():
    assert _display_width("abc") == 3


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
    assert "── 警告/错误 ── 0-0/0" in content
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
    assert label == "警告 8 | 1-3/8"
    ui.history_scroll = 5
    visible, label = ui._slice_history_lines(lines, 3)
    assert visible[0].endswith("warning 5")
    assert label == "警告 8 | 6-8/8"


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
    assert label == "警告 2 / 错误 1 | 1-3/3"


def test_progress_ui_empty_history_label_uses_zero_range_only():
    ui = ExportProgressUI(stream=DummyStream())
    lines = ui._plain_history_lines(80)
    visible, label = ui._slice_display_lines("history", lines, 3)
    assert visible == ["  - 暂无", "", ""]
    assert label == "0-0/0"


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
