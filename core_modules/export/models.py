"""导出模块数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class RepoRef:
    """仓库引用，对应语雀知识库。"""
    group_login: str
    book_slug: str
    book_id: int | None = None
    name: str | None = None
    namespace: str | None = None
    url: str | None = None


@dataclass(slots=True)
class TocNode:
    """目录树节点，对应语雀知识库的目录结构。"""
    uuid: str | None
    node_type: str
    title: str
    doc_id: int | None = None
    slug: str | None = None
    url: str | None = None
    visible: bool = True
    children: list["TocNode"] = field(default_factory=list)


@dataclass(slots=True)
class DocOutputPaths:
    """单篇文档的输出文件路径。"""
    doc_dir: Path
    markdown_path: Path
    assets_dir: Path
    raw_json_path: Path | None = None
    raw_lake_path: Path | None = None


@dataclass(slots=True)
class DocExportState:
    """单篇文档的导出状态，写入 checkpoint。"""
    stage: str = "pending"
    markdown_path: str | None = None
    assets_dir: str | None = None
    failed_resource_urls: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    warning_count: int = 0
    download_count: int = 0
    download_failed_count: int = 0


@dataclass(slots=True)
class ExportOptions:
    """导出行为的配置选项。"""
    repo_input: str
    output_dir: Path
    resume: bool = True
    strict: bool = False
    request_interval: float = 0.2
    max_docs: int | None = None
    selected_doc_ids: set[int] | None = None
    offline_assets: bool = True
    assets_dir_name: str = "assets"
    fail_on_asset_error: bool = False
    attachment_suffixes: list[str] = field(default_factory=lambda: ["*"])


@dataclass(slots=True)
class ExportResult:
    """导出最终结果，汇总全部统计信息。"""
    repo: RepoRef
    exported_docs: int = 0
    skipped_docs: int = 0
    failed_docs: int = 0
    written_files: list[Path] = field(default_factory=list)
    failed_items: list[str] = field(default_factory=list)
    rewritten_links: int = 0
    total_warnings: int = 0
    total_downloaded: int = 0
    total_download_failed: int = 0
    elapsed_seconds: float | None = None


@dataclass(slots=True)
class ProgressSnapshot:
    """导出进度的快照，通过回调传递给 UI。"""
    current_doc_title: str = ""
    current_stage: str = "准备中"
    processed_docs: int = 0
    total_docs: int = 0
    completed_docs: int = 0
    skipped_docs: int = 0
    failed_docs: int = 0
    waiting_docs: int = 0
    warning_count: int = 0
    latest_warning: str | None = None
    new_warnings: list[str] = field(default_factory=list)
    latest_error: str | None = None
    latest_event: str = "初始化"
    active_tasks: list[str] = field(default_factory=list)
    recent_completed: list[str] = field(default_factory=list)
    recent_failed: list[str] = field(default_factory=list)
    waiting_preview: list[str] = field(default_factory=list)
    rate_limit_limit: int | None = None
    rate_limit_remaining: int | None = None
    rate_limit_reset: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    # 当前文档级统计
    current_doc_warnings: int = 0
    current_doc_resources: int = 0
    current_doc_downloaded: int = 0
    current_doc_elapsed_ms: int = 0


@dataclass(slots=True)
class CheckpointState:
    """导出断点状态，写入 JSON 持久化。"""
    repo: dict[str, str | int | None]
    export_started_at: str
    completed_doc_ids: list[int] = field(default_factory=list)
    failed_doc_ids: list[int] = field(default_factory=list)
    doc_path_map: dict[str, str] = field(default_factory=dict)
    last_success_doc_id: int | None = None
    doc_states: dict[str, DocExportState] = field(default_factory=dict)
    doc_slug_map: dict[str, str] = field(default_factory=dict)
