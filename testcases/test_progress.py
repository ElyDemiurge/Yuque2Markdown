"""Tests for progress module."""
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


def test_progress_ui_warning_history():
    stream = DummyStream()
    ui = ExportProgressUI(stream=stream)
    snapshot = ProgressSnapshot(latest_warning="warning 1")
    ui.update(snapshot)
    assert len(ui.history) == 1
    assert ui.history[0][0] == "WARN"


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
    assert label == "告警 1-3/8"
    ui.history_scroll = 5
    visible, label = ui._slice_history_lines(lines, 3)
    assert visible[0].endswith("warning 5")
    assert label == "告警 6-8/8"


def test_stage_color():
    ui = ExportProgressUI(stream=DummyStream())
    assert ui._stage_color("已完成") == ui.GREEN
    assert ui._stage_color("导出失败") == ui.RED
    assert ui._stage_color("限流等待") == ui.YELLOW


if __name__ == "__main__":
    import traceback

    tests = [obj for name, obj in globals().items() if name.startswith("test_") and callable(obj)]
    passed = failed = 0
    for test in tests:
        try:
            test()
            print(f"  PASS: {test.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {test.__name__}: {e}")
            traceback.print_exc()
            failed += 1
    print(f"\nResults: {passed} passed, {failed} failed")
