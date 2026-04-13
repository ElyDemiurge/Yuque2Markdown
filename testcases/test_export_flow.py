"""Tests for export flow."""
import sys
sys.path.insert(0, ".")

from pathlib import Path

from core_modules.export.exporter import Exporter
from core_modules.export.models import ExportOptions, ProgressSnapshot, RepoRef


class FakeClient:
    def __init__(self) -> None:
        self.last_rate_limit = {"limit": 500, "remaining": 498, "reset": "1234567890"}

    def get_repo_detail(self, group_login: str, book_slug: str):
        return {"data": {"id": 1, "name": "测试库", "namespace": group_login}}

    def get_all_repo_docs(self, group_login: str, book_slug: str):
        return [
            {"id": 11, "slug": "doc-1", "title": "文档1"},
            {"id": 12, "slug": "doc-2", "title": "文档2"},
        ]

    def get_repo_toc(self, group_login: str, book_slug: str):
        return {
            "data": [
                {"type": "DOC", "title": "文档1", "doc_id": 11, "slug": "doc-1"},
                {"type": "DOC", "title": "文档2", "doc_id": 12, "slug": "doc-2"},
            ]
        }

    def get_doc_detail(self, group_login: str, book_slug: str, doc_id_or_slug: str):
        if str(doc_id_or_slug) == "11":
            body = "正文\n\n![图](https://example.com/a.png)\n\n[下一篇](https://www.yuque.com/cyberangel/rg9gdm/doc-2)"
            return {"data": {"id": 11, "slug": "doc-1", "title": "文档1", "format": "markdown", "body": body}}
        return {"data": {"id": 12, "slug": "doc-2", "title": "文档2", "format": "markdown", "body": "# 文档2\n\n正文2"}}

    def fetch_binary(self, url: str) -> bytes:
        return b"image-bytes"


def test_export_repo_writes_markdown_file(tmp_path: Path) -> None:
    exporter = Exporter(FakeClient())
    repo = RepoRef(group_login="cyberangel", book_slug="rg9gdm")
    options = ExportOptions(repo_input="cyberangel/rg9gdm", output_dir=tmp_path, request_interval=0)
    result = exporter.export_repo(repo, options)
    assert result.exported_docs == 2
    files = list(tmp_path.rglob("*.md"))
    assert files
    assert any("文档1" in file.read_text(encoding="utf-8") for file in files)


def test_export_repo_creates_doc_directory_and_assets(tmp_path: Path) -> None:
    exporter = Exporter(FakeClient())
    repo = RepoRef(group_login="cyberangel", book_slug="rg9gdm")
    options = ExportOptions(repo_input="cyberangel/rg9gdm", output_dir=tmp_path, request_interval=0)
    exporter.export_repo(repo, options)

    doc_dir = tmp_path / "测试库" / "文档1"
    markdown_path = doc_dir / "文档1.md"
    asset_files = list((doc_dir / "assets").iterdir())

    assert doc_dir.is_dir()
    assert markdown_path.exists()
    content = markdown_path.read_text(encoding="utf-8")
    assert "./assets/" in content
    assert "../文档2/文档2.md" in content
    assert asset_files


def test_export_repo_reports_progress_events(tmp_path: Path) -> None:
    snapshots: list[ProgressSnapshot] = []

    def on_progress(snapshot: ProgressSnapshot) -> None:
        snapshots.append(
            ProgressSnapshot(
                current_doc_title=snapshot.current_doc_title,
                current_stage=snapshot.current_stage,
                processed_docs=snapshot.processed_docs,
                total_docs=snapshot.total_docs,
                completed_docs=snapshot.completed_docs,
                skipped_docs=snapshot.skipped_docs,
                failed_docs=snapshot.failed_docs,
                waiting_docs=snapshot.waiting_docs,
                warning_count=snapshot.warning_count,
                latest_warning=snapshot.latest_warning,
                latest_error=snapshot.latest_error,
                latest_event=snapshot.latest_event,
                active_tasks=list(snapshot.active_tasks),
                recent_completed=list(snapshot.recent_completed),
                recent_failed=list(snapshot.recent_failed),
                waiting_preview=list(snapshot.waiting_preview),
                rate_limit_limit=snapshot.rate_limit_limit,
                rate_limit_remaining=snapshot.rate_limit_remaining,
                rate_limit_reset=snapshot.rate_limit_reset,
                details=dict(snapshot.details),
            )
        )

    exporter = Exporter(FakeClient(), progress_callback=on_progress)
    repo = RepoRef(group_login="cyberangel", book_slug="rg9gdm")
    options = ExportOptions(repo_input="cyberangel/rg9gdm", output_dir=tmp_path, request_interval=0)
    result = exporter.export_repo(repo, options)

    assert result.exported_docs == 2
    assert snapshots
    assert snapshots[0].total_docs == 2
    assert any(snapshot.current_stage == "离线化附件" for snapshot in snapshots)
    assert any(snapshot.active_tasks for snapshot in snapshots)
    assert any(snapshot.waiting_preview for snapshot in snapshots[:-1])
    assert snapshots[-1].current_stage == "已完成"
    assert snapshots[-1].completed_docs == 2
    assert snapshots[-1].processed_docs == 2
    assert snapshots[-1].waiting_docs == 0
    assert snapshots[-1].recent_completed
    assert snapshots[-1].rate_limit_limit == 500
    assert snapshots[-1].rate_limit_remaining == 498
    assert snapshots[-1].rate_limit_reset == "1234567890"
    assert snapshots[0].details["log_path"].endswith("export.log")


class FailingClient(FakeClient):
    def get_doc_detail(self, group_login: str, book_slug: str, doc_id_or_slug: str):
        raise RuntimeError("boom")


def test_export_repo_logs_failure_on_exception(tmp_path: Path) -> None:
    exporter = Exporter(FailingClient())
    repo = RepoRef(group_login="cyberangel", book_slug="rg9gdm")
    options = ExportOptions(repo_input="cyberangel/rg9gdm", output_dir=tmp_path, request_interval=0, strict=True)

    try:
        exporter.export_repo(repo, options)
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected RuntimeError")

    log_path = tmp_path / "测试库" / "export.log"
    content = log_path.read_text(encoding="utf-8")
    assert "导出失败" in content
    assert "boom" in content


if __name__ == "__main__":
    import tempfile
    tests = [
        obj
        for name, obj in globals().items()
        if name.startswith("test_") and callable(obj)
    ]
    passed = 0
    failed = 0
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
            failed += 1
    print(f"\nResults: {passed} passed, {failed} failed")
