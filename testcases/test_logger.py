"""Tests for logger module."""
import sys
sys.path.insert(0, ".")

import tempfile
from pathlib import Path
from core_modules.export.logger import ExportLogger


def test_logger_write_and_read(tmp_path):
    log_path = tmp_path / "test.log"
    log = ExportLogger(log_path)
    log.info("test message")
    log_path_str = log_path.read_text(encoding="utf-8")
    assert "test message" in log_path_str
    assert "[INFO" in log_path_str


def test_logger_multiple_levels(tmp_path):
    log_path = tmp_path / "test.log"
    log = ExportLogger(log_path)
    log.debug("debug msg")
    log.info("info msg")
    log.warning("warn msg")
    log.error("error msg")
    content = log_path.read_text(encoding="utf-8")
    assert "[DEBUG" in content
    assert "[INFO" in content
    assert "[WARN" in content
    assert "[ERROR" in content


def test_logger_export_events(tmp_path):
    log_path = tmp_path / "test.log"
    log = ExportLogger(log_path)
    log.export_started("MyRepo", "/output", 10)
    log.export_finished(exported=8, skipped=1, failed=1, warnings=2, resources_downloaded=20, resources_failed=0, rewritten_links=5)
    content = log_path.read_text(encoding="utf-8")
    assert "导出开始" in content
    assert "导出完成" in content


def test_logger_doc_events(tmp_path):
    log_path = tmp_path / "test.log"
    log = ExportLogger(log_path)
    log.doc_started("Doc 1")
    log.doc_markdown_done("Doc 1", warnings=0, resources=5)
    log.doc_assets_done("Doc 1", downloaded=5, failed=0, rewritten=2)
    log.doc_completed("Doc 1", warnings=0)
    content = log_path.read_text(encoding="utf-8")
    assert "开始: Doc 1" in content
    assert "Markdown 完成" in content
    assert "资源完成" in content
    assert "完成: Doc 1" in content


def test_logger_skip_and_fail(tmp_path):
    log_path = tmp_path / "test.log"
    log = ExportLogger(log_path)
    log.doc_skipped("Doc Skipped")
    log.doc_failed("Doc Failed", "network error")
    content = log_path.read_text(encoding="utf-8")
    assert "跳过: Doc Skipped" in content
    assert "失败: Doc Failed" in content


def test_logger_write_failure_tracked(tmp_path):
    """When log write fails, error should be tracked, not silently ignored."""
    # Use a path that's guaranteed to be unreadable as a directory
    log_path = tmp_path / "readonly_dir" / "test.log"
    log = ExportLogger(log_path)
    log.info("this should fail")
    status = log.get_status()
    assert status["failures"] >= 1
    assert status["last_error"] is not None


def test_logger_get_status(tmp_path):
    log_path = tmp_path / "test.log"
    log = ExportLogger(log_path)
    log.info("msg1")
    log.info("msg2")
    log.info("msg3")
    status = log.get_status()
    assert status["total_writes"] == 3
    assert status["failures"] == 0
    assert status["last_error"] is None
    assert "test.log" in status["path"]


def test_logger_elapsed_timing(tmp_path):
    log_path = tmp_path / "test.log"
    log = ExportLogger(log_path)
    log.info("first")
    import time
    time.sleep(0.05)
    log.info("second")
    content = log_path.read_text(encoding="utf-8")
    lines = content.strip().split("\n")
    assert len(lines) == 2
