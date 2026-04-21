"""导出流程测试。"""
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
    assert any(snapshot.current_stage == "下载图片并执行附件本地化" for snapshot in snapshots)
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


def test_export_repo_removes_current_doc_from_waiting_queue_when_processing_starts(tmp_path: Path) -> None:
    snapshots: list[dict[str, object]] = []

    def on_progress(snapshot: ProgressSnapshot) -> None:
        waiting_titles = snapshot.details.get("_waiting_titles")
        snapshots.append(
            {
                "current_doc_title": snapshot.current_doc_title,
                "current_stage": snapshot.current_stage,
                "waiting_preview": list(snapshot.waiting_preview),
                "waiting_titles": list(waiting_titles) if isinstance(waiting_titles, list) else None,
            }
        )

    exporter = Exporter(FakeClient(), progress_callback=on_progress)
    repo = RepoRef(group_login="cyberangel", book_slug="rg9gdm")
    options = ExportOptions(repo_input="cyberangel/rg9gdm", output_dir=tmp_path, request_interval=0)

    result = exporter.export_repo(repo, options)

    assert result.exported_docs == 2
    processing_snapshot = next(
        snapshot
        for snapshot in snapshots
        if snapshot["current_stage"] == "准备导出文档" and snapshot["current_doc_title"] == "文档1"
    )
    assert processing_snapshot["waiting_preview"] == ["文档2"]
    assert processing_snapshot["waiting_titles"] == ["文档2"]


class AttachmentWarningClient(FakeClient):
    def get_all_repo_docs(self, group_login: str, book_slug: str):
        return [{"id": 21, "slug": "doc-attachment", "title": "附件文档"}]

    def get_repo_toc(self, group_login: str, book_slug: str):
        return {"data": [{"type": "DOC", "title": "附件文档", "doc_id": 21, "slug": "doc-attachment"}]}

    def get_doc_detail(self, group_login: str, book_slug: str, doc_id_or_slug: str):
        body = "[附件](https://www.yuque.com/attachments/yuque/0/2022/pdf/demo.pdf)"
        return {"data": {"id": 21, "slug": "doc-attachment", "title": "附件文档", "format": "markdown", "body": body}}


def test_export_repo_emits_attachment_warning_without_download_failure(tmp_path: Path) -> None:
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
                new_warnings=list(snapshot.new_warnings),
            )
        )

    exporter = Exporter(AttachmentWarningClient(), progress_callback=on_progress)
    repo = RepoRef(group_login="cyberangel", book_slug="rg9gdm")
    options = ExportOptions(repo_input="cyberangel/rg9gdm", output_dir=tmp_path, request_interval=0)
    result = exporter.export_repo(repo, options)

    assert result.exported_docs == 1
    assert any(
        "使用 Token 登录时无法下载附件" in warning
        for snapshot in snapshots
        for warning in snapshot.new_warnings
    )


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


def test_export_repo_warns_when_selected_docs_do_not_match_actual_queue(tmp_path: Path) -> None:
    snapshots: list[ProgressSnapshot] = []

    def on_progress(snapshot: ProgressSnapshot) -> None:
        snapshots.append(
            ProgressSnapshot(
                total_docs=snapshot.total_docs,
                warning_count=snapshot.warning_count,
                latest_warning=snapshot.latest_warning,
                new_warnings=list(snapshot.new_warnings),
                details=dict(snapshot.details),
            )
        )

    exporter = Exporter(FakeClient(), progress_callback=on_progress)
    repo = RepoRef(group_login="cyberangel", book_slug="rg9gdm")
    options = ExportOptions(
        repo_input="cyberangel/rg9gdm",
        output_dir=tmp_path,
        request_interval=0,
        selected_doc_ids={11, 12, 13},
    )

    result = exporter.export_repo(repo, options)

    assert result.exported_docs == 2
    assert any("实际可导出 2 篇" in (snapshot.latest_warning or "") for snapshot in snapshots)
    log_path = tmp_path / "测试库" / "export.log"
    assert "实际可导出 2 篇" in log_path.read_text(encoding="utf-8")
