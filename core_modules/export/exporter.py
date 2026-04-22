"""知识库导出器实现。

本模块负责知识库目录遍历、单文档导出、资源本地化、断点维护和进度回调。
"""

from __future__ import annotations

import time
from collections import deque
from pathlib import Path
from typing import Callable

from core_modules.export.checkpoint import create_checkpoint, load_checkpoint, save_checkpoint
from core_modules.export.client import YuqueClient
from core_modules.export.errors import ExportCancelledError, ExportError, YuquePermissionError, YuqueRateLimitError
from core_modules.export.file_naming import sanitize_name, unique_name
from core_modules.export.logger import ExportLogger
from core_modules.export.models import (
    CheckpointState,
    DocExportState,
    DocOutputPaths,
    ExportOptions,
    ExportResult,
    ProgressSnapshot,
    RepoRef,
    TocNode,
)
from core_modules.export.toc_builder import build_toc_tree
from core_modules.export.writer import ensure_dir, write_json_file, write_text_file
from core_modules.lake.converter import render_doc_markdown
from core_modules.lake.localizer import is_critical_resource_failure, localize_markdown_assets


def build_doc_markdown_result(
    doc_data: dict | None = None,
    *,
    render_result=None,
    markdown_path: Path,
    assets_dir: Path,
    offline_assets: bool,
    attachment_suffixes: list[str],
    allow_attachment_downloads: bool = False,
    fetch_binary=None,
    doc_slug_map: dict[str, str] | None = None,
):
    """构建单篇文档最终 Markdown 结果。

    说明:
        导出流程与“根据 .lake 重新生成 Markdown”共用同一套资源本地化逻辑，避免两处
        处理结果不一致。
    """
    if render_result is None:
        if doc_data is None:
            raise ValueError("doc_data 和 render_result 不能同时为空")
        render_result = render_doc_markdown(doc_data)
    if not offline_assets:
        return render_result
    # 启用离线资源后，优先复用本地 assets；缺失时再尝试下载并改写链接。
    return localize_markdown_assets(
        render_result,
        assets_dir=assets_dir,
        fetch_binary=fetch_binary,
        doc_slug_map=doc_slug_map,
        current_markdown_path=markdown_path,
        attachment_suffixes=attachment_suffixes,
        allow_attachment_downloads=allow_attachment_downloads,
    )


class Exporter:
    """负责按目录树导出知识库文档与资源。"""
    def __init__(self, client: YuqueClient, progress_callback: Callable[[ProgressSnapshot], None] | None = None) -> None:
        """初始化导出器。"""
        self.client = client
        self.progress_callback = progress_callback

    def export_repo(self, repo: RepoRef, options: ExportOptions) -> ExportResult:
        """导出整个知识库，并汇总导出结果。"""
        overall_start = time.monotonic()
        self._check_cancel()

        repo_payload = self.client.get_repo_detail(repo.group_login, repo.book_slug)
        repo_data = repo_payload.get("data", {})
        repo.book_id = repo_data.get("id")
        repo.name = repo_data.get("name") or repo.name or repo.book_slug
        repo.namespace = repo_data.get("namespace")

        repo_dir = options.output_dir / sanitize_name(repo.name or repo.book_slug)
        ensure_dir(repo_dir)

        log_path = repo_dir / "export.log"
        log = ExportLogger(log_path)

        checkpoint = None if not options.resume else load_checkpoint(repo_dir)
        if checkpoint is None:
            checkpoint = create_checkpoint(repo)
            save_checkpoint(repo_dir, checkpoint)

        docs = self.client.get_all_repo_docs(repo.group_login, repo.book_slug)
        docs_by_id = {doc.get("id"): doc for doc in docs if isinstance(doc.get("id"), int)}

        toc_payload = self.client.get_repo_toc(repo.group_login, repo.book_slug)
        raw_toc = toc_payload.get("data", [])
        toc_tree = build_toc_tree(raw_toc)

        repo_slug_map = self._build_repo_slug_map(repo_dir, toc_tree, docs_by_id, selected_doc_ids=options.selected_doc_ids)
        checkpoint.doc_slug_map.update(repo_slug_map)

        result = ExportResult(repo=repo)
        # 先收集实际待导出的标题列表，用于初始化进度条总量与等待预览。
        queue = self._collect_doc_titles(toc_tree, checkpoint, options)
        total_docs = len(queue)
        selection_warning = None
        if options.selected_doc_ids is not None and len(options.selected_doc_ids) != total_docs:
            selection_warning = (
                f"选择了 {len(options.selected_doc_ids)} 篇文档，实际可导出 {total_docs} 篇；"
                "可能有文档已删除、无权限或不在当前目录树中"
            )
        progress = ProgressSnapshot(
            export_started_monotonic=overall_start,
            total_docs=total_docs,
            waiting_docs=total_docs,
            latest_event=f"开始导出知识库 {repo.name or repo.book_slug}",
            waiting_preview=queue[:5],
            recent_completed=[],
            recent_failed=[],
            details={"log_path": str(log_path), "_waiting_titles": list(queue)},
        )
        log.export_started(repo.name or repo.book_slug, str(repo_dir), total_docs)
        if selection_warning:
            log.warning(selection_warning)
            progress.warning_count = 1
            progress.latest_warning = selection_warning
            progress.new_warnings = [selection_warning]
        self._emit_progress(progress)

        used_names: dict[Path, set[str]] = {}
        try:
            self._export_nodes(
                repo=repo,
                nodes=toc_tree,
                current_dir=repo_dir,
                repo_dir=repo_dir,
                docs_by_id=docs_by_id,
                checkpoint=checkpoint,
                result=result,
                options=options,
                used_names=used_names,
                progress=progress,
                log=log,
            )
        except ExportCancelledError:
            log.warning("导出已中止")
            raise
        except Exception as exc:
            log.export_failed(str(exc))
            raise

        elapsed = time.monotonic() - overall_start
        result.elapsed_seconds = elapsed
        result.total_warnings = progress.warning_count
        total_downloaded = sum(
            getattr(checkpoint.doc_states.get(k), "download_count", 0) for k in checkpoint.doc_states
        )
        total_failed = sum(
            getattr(checkpoint.doc_states.get(k), "download_failed_count", 0) for k in checkpoint.doc_states
        )
        result.total_downloaded = total_downloaded
        result.total_download_failed = total_failed

        save_checkpoint(repo_dir, checkpoint)
        log.export_finished(
            exported=result.exported_docs,
            skipped=result.skipped_docs,
            failed=result.failed_docs,
            warnings=result.total_warnings,
            resources_downloaded=total_downloaded,
            resources_failed=total_failed,
            rewritten_links=result.rewritten_links,
        )
        self._emit_progress(
            progress,
            current_stage="已完成",
            current_doc_title="",
            current_doc_started_monotonic=0.0,
            latest_event=f"导出完成，成功 {result.exported_docs} 篇，跳过 {result.skipped_docs} 篇，失败 {result.failed_docs} 篇",
        )
        return result

    def _export_nodes(
        self,
        repo: RepoRef,
        nodes: list[TocNode],
        current_dir: Path,
        repo_dir: Path,
        docs_by_id: dict,
        checkpoint: CheckpointState,
        result: ExportResult,
        options: ExportOptions,
        used_names: dict[Path, set[str]],
        progress: ProgressSnapshot,
        log: ExportLogger,
    ) -> None:
        """递归遍历目录树并导出文档节点。"""
        name_pool = used_names.setdefault(current_dir, set())
        for node in nodes:
            self._check_cancel()
            if options.max_docs is not None and result.exported_docs >= options.max_docs:
                return
            safe_name = unique_name(sanitize_name(node.title), name_pool, suffix=str(node.doc_id) if node.doc_id else None)
            if node.node_type == "TITLE":
                if self._has_selected_docs(node.children, options.selected_doc_ids):
                    next_dir = current_dir / safe_name
                    ensure_dir(next_dir)
                    self._export_nodes(repo, node.children, next_dir, repo_dir, docs_by_id, checkpoint, result, options, used_names, progress, log)
                continue

            if node.node_type == "LINK":
                # 链接节点只在全量导出时保留为跳转文档；按选中文档导出时直接忽略。
                if options.selected_doc_ids is not None:
                    continue
                content = f"# {node.title}\n\n原始链接：{node.url or ''}\n"
                path = current_dir / f"{safe_name}.md"
                ensure_dir(current_dir)
                write_text_file(path, content)
                result.written_files.append(path)
                continue

            if node.node_type != "DOC":
                continue

            doc_id = node.doc_id
            if options.selected_doc_ids is not None and (not doc_id or doc_id not in options.selected_doc_ids):
                continue
            if doc_id and doc_id in checkpoint.completed_doc_ids:
                result.skipped_docs += 1
                waiting_preview = self._advance_waiting_preview(progress, node.title)
                recent_completed = self._push_recent(progress.recent_completed, f"跳过 {node.title}")
                self._emit_progress(
                    progress,
                    processed_docs=progress.processed_docs + 1,
                    skipped_docs=result.skipped_docs,
                    waiting_docs=max(0, progress.waiting_docs - 1),
                    waiting_preview=waiting_preview,
                    recent_completed=recent_completed,
                    current_doc_title=node.title,
                    current_stage="跳过已完成文档",
                    active_tasks=[f"跳过 {node.title}"],
                    latest_event=f"跳过 {node.title}",
                )
                log.doc_skipped(node.title)
                continue

            waiting_preview = self._advance_waiting_preview(progress, node.title)
            self._emit_progress(
                progress,
                current_doc_title=node.title,
                current_stage="准备导出文档",
                waiting_preview=waiting_preview,
                active_tasks=[
                    f"读取文档详情: {node.title}",
                    f"等待后续: {', '.join(waiting_preview[:2])}" if waiting_preview[:2] else "等待后续: -",
                ],
                latest_event=f"开始处理 {node.title}",
            )
            try:
                self._export_single_doc(
                    repo=repo,
                    node=node,
                    safe_name=safe_name,
                    current_dir=current_dir,
                    repo_dir=repo_dir,
                    docs_by_id=docs_by_id,
                    checkpoint=checkpoint,
                    result=result,
                    options=options,
                    progress=progress,
                    log=log,
                )
            except (YuquePermissionError, YuqueRateLimitError, ExportError) as exc:
                if doc_id and doc_id not in checkpoint.failed_doc_ids:
                    checkpoint.failed_doc_ids.append(doc_id)
                self._ensure_doc_state(checkpoint, doc_id).stage = "failed"
                save_checkpoint(repo_dir, checkpoint)
                result.failed_docs += 1
                result.failed_items.append(f"{node.title}: {exc}")
                recent_failed = self._push_recent(progress.recent_failed, f"{node.title}: {exc}")
                waiting_preview = self._advance_waiting_preview(progress, node.title)
                self._emit_progress(
                    progress,
                    processed_docs=progress.processed_docs + 1,
                    failed_docs=result.failed_docs,
                    waiting_docs=max(0, progress.waiting_docs - 1),
                    waiting_preview=waiting_preview,
                    recent_failed=recent_failed,
                    current_doc_title=node.title,
                    current_stage="导出失败",
                    active_tasks=[f"失败: {node.title}"],
                    latest_event=f"{node.title} 导出失败",
                    latest_error=f"{node.title}: {exc}",
                )
                log.doc_failed(node.title, str(exc))
                if options.strict or isinstance(exc, YuqueRateLimitError):
                    raise
            except Exception as exc:
                if doc_id and doc_id not in checkpoint.failed_doc_ids:
                    checkpoint.failed_doc_ids.append(doc_id)
                self._ensure_doc_state(checkpoint, doc_id).stage = "failed"
                save_checkpoint(repo_dir, checkpoint)
                result.failed_docs += 1
                result.failed_items.append(f"{node.title}: {exc}")
                recent_failed = self._push_recent(progress.recent_failed, f"{node.title}: {exc}")
                waiting_preview = self._advance_waiting_preview(progress, node.title)
                self._emit_progress(
                    progress,
                    processed_docs=progress.processed_docs + 1,
                    failed_docs=result.failed_docs,
                    waiting_docs=max(0, progress.waiting_docs - 1),
                    waiting_preview=waiting_preview,
                    recent_failed=recent_failed,
                    current_doc_title=node.title,
                    current_stage="导出失败",
                    active_tasks=[f"失败: {node.title}"],
                    latest_event=f"{node.title} 导出失败",
                    latest_error=f"{node.title}: {exc}",
                )
                log.doc_failed(node.title, str(exc))
                if options.strict:
                    raise

    def _export_single_doc(
        self,
        *,
        repo: RepoRef,
        node: TocNode,
        safe_name: str,
        current_dir: Path,
        repo_dir: Path,
        docs_by_id: dict,
        checkpoint: CheckpointState,
        result: ExportResult,
        options: ExportOptions,
        progress: ProgressSnapshot,
        log: ExportLogger,
    ) -> None:
        """导出单篇文档及其相关资源。"""
        doc_start = time.monotonic()
        self._check_cancel()

        doc_id = node.doc_id
        doc_meta = docs_by_id.get(doc_id) if doc_id else None
        doc_slug = node.slug or (doc_meta or {}).get("slug")
        doc_identifier = doc_id or doc_slug
        if not doc_identifier:
            raise ExportError(f"缺少文档标识: {node.title}")

        log.doc_started(node.title)
        if hasattr(self.client, "set_debug_logger"):
            self.client.set_debug_logger(lambda message, doc_title=node.title: log.debug(f"[{doc_title}] {message}"))
        self._emit_progress(
            progress,
            current_doc_elapsed_ms=0,
            current_doc_started_monotonic=doc_start,
            current_doc_warnings=0,
            current_doc_resources=0,
            current_doc_downloaded=0,
        )

        output_paths = self._build_doc_output_paths(current_dir, safe_name, options)
        state = self._ensure_doc_state(checkpoint, doc_id)
        state.markdown_path = str(output_paths.markdown_path)
        state.assets_dir = str(output_paths.assets_dir)

        doc_payload = self.client.get_doc_detail(repo.group_login, repo.book_slug, str(doc_identifier))
        self._check_cancel()

        if output_paths.raw_json_path:
            write_json_file(output_paths.raw_json_path, doc_payload)

        doc_data = doc_payload.get("data", {})
        raw_lake = str(doc_data.get("body_lake") or "")
        if output_paths.raw_lake_path and (raw_lake or str(doc_data.get("format") or "").lower() == "lake"):
            write_text_file(output_paths.raw_lake_path, raw_lake)

        self._emit_progress(
            progress,
            current_doc_title=node.title,
            current_doc_started_monotonic=doc_start,
            current_stage="渲染 Markdown",
            active_tasks=[f"渲染 Markdown: {node.title}", f"写入目录: {output_paths.markdown_path.parent.name}"],
            latest_event=f"已获取文档详情: {node.title}",
            current_doc_elapsed_ms=int((time.monotonic() - doc_start) * 1000),
        )
        render_result = render_doc_markdown(doc_data)
        self._check_cancel()
        state.warnings = list(render_result.warnings)
        state.warning_count = len(render_result.warnings)

        if render_result.warnings:
            warning_messages = [f"{node.title}: {warning}" for warning in render_result.warnings]
            for w in render_result.warnings:
                log.warning(f"[{node.title}] {w}")
            self._emit_progress(
                progress,
                warning_count=progress.warning_count + len(render_result.warnings),
                current_doc_warnings=state.warning_count,
                current_doc_resources=len(render_result.resources),
                active_tasks=[f"渲染完成: {node.title}", f"发现 {len(render_result.warnings)} 个警告，继续资源处理"],
                latest_warning=f"{node.title}: {render_result.warnings[-1]}",
                new_warnings=warning_messages,
                latest_event=f"{node.title} 渲染完成，存在警告",
            )
        else:
            self._emit_progress(
                progress,
                current_doc_warnings=0,
                current_doc_resources=len(render_result.resources),
                new_warnings=[],
            )
            self._emit_progress(
                progress,
                active_tasks=[f"渲染完成: {node.title}"],
                new_warnings=[],
            )

        log.doc_markdown_done(node.title, state.warning_count, len(render_result.resources))

        # 如果启用离线资源，先下载图片并改写链接，再写盘；否则直接写原始 Markdown。
        final_result = render_result
        if options.offline_assets:
            # 导出与根据 .lake 重新生成 Markdown 使用同一套资源处理代码，避免两处逻辑不一致。
            self._emit_progress(
                progress,
                current_doc_title=node.title,
                current_doc_started_monotonic=doc_start,
                current_stage="下载图片并执行附件本地化",
                active_tasks=[f"处理资源: {node.title}", f"改写内部链接: {node.title}"],
                latest_event=f"正在处理 {node.title} 的资源",
            )
            previous_warning_count = len(state.warnings)
            final_result = build_doc_markdown_result(
                render_result=render_result,
                markdown_path=output_paths.markdown_path,
                assets_dir=output_paths.assets_dir,
                offline_assets=True,
                attachment_suffixes=options.attachment_suffixes,
                allow_attachment_downloads=options.allow_attachment_downloads,
                fetch_binary=self.client.fetch_binary,
                doc_slug_map=checkpoint.doc_slug_map,
            )
            self._check_cancel()
            rewritten_count = final_result.rewritten_links
            result.rewritten_links += rewritten_count
            download_count = sum(
                1 for r in final_result.resources if r.kind in {"image", "attachment"} and r.local_path and not r.failed
            )
            download_failed = sum(1 for r in final_result.resources if r.kind in {"image", "attachment"} and r.failed)
            state.download_count = download_count
            state.download_failed_count = download_failed
            state.failed_resource_urls = [r.normalized_url for r in final_result.resources if r.failed]
            state.warnings = list(final_result.warnings)
            state.warning_count = len(final_result.warnings)
            save_checkpoint(repo_dir, checkpoint)

            log.doc_assets_done(node.title, download_count, download_failed, rewritten_count)

            new_asset_warnings = final_result.warnings[previous_warning_count:]
            for warning in new_asset_warnings:
                log.warning(f"[{node.title}] {warning}")

            warning_messages = [f"{node.title}: {warning}" for warning in new_asset_warnings]
            if state.failed_resource_urls:
                latest_warning = f"{node.title}: {len(state.failed_resource_urls)} 个资源下载失败"
                self._emit_progress(
                    progress,
                    warning_count=progress.warning_count + len(new_asset_warnings),
                    current_doc_warnings=state.warning_count,
                    current_doc_downloaded=download_count,
                    active_tasks=[f"资源处理完成: {node.title}"],
                    latest_warning=latest_warning,
                    new_warnings=warning_messages,
                    latest_event=f"{node.title} 资源处理完成",
                )
            else:
                self._emit_progress(
                    progress,
                    warning_count=progress.warning_count + len(new_asset_warnings),
                    current_doc_warnings=state.warning_count,
                    current_doc_downloaded=download_count,
                    active_tasks=[f"资源处理完成: {node.title}"],
                    latest_warning=warning_messages[-1] if warning_messages else None,
                    new_warnings=warning_messages,
                    latest_event=f"{node.title} 资源处理完成",
                )
            # 总是更新下载计数
            self._emit_progress(
                progress,
                current_doc_downloaded=download_count,
                new_warnings=[],
            )
            state.stage = "assets_localized"
            critical_failures = [
                resource for resource in final_result.resources if resource.failed and is_critical_resource_failure(resource)
            ]
            if options.fail_on_asset_error and critical_failures:
                raise ExportError(f"资源下载失败: {len(critical_failures)} 个")
        else:
            state.stage = "markdown_written"
            save_checkpoint(repo_dir, checkpoint)

        # 最终 Markdown（含资源处理结果）写入文件。
        write_text_file(output_paths.markdown_path, final_result.markdown)

        self._mark_doc_completed(
            checkpoint=checkpoint,
            doc_id=doc_id,
            markdown_path=output_paths.markdown_path,
        )
        state.stage = "completed"
        result.exported_docs += 1
        result.written_files.append(output_paths.markdown_path)
        save_checkpoint(repo_dir, checkpoint)
        recent_completed = self._push_recent(progress.recent_completed, node.title)
        waiting_preview = self._advance_waiting_preview(progress, node.title)
        self._emit_progress(
            progress,
            processed_docs=progress.processed_docs + 1,
            completed_docs=result.exported_docs,
            waiting_docs=max(0, progress.waiting_docs - 1),
            waiting_preview=waiting_preview,
            recent_completed=recent_completed,
            current_doc_title=node.title,
            current_doc_started_monotonic=doc_start,
            current_stage="文档完成",
            active_tasks=[f"完成: {node.title}"],
            latest_event=f"已完成 {node.title}",
            current_doc_elapsed_ms=int((time.monotonic() - doc_start) * 1000),
        )
        log.doc_completed(node.title, state.warning_count)
        if hasattr(self.client, "set_debug_logger"):
            self.client.set_debug_logger(None)

    def _check_cancel(self) -> None:
        """把取消检查委托给客户端。"""
        if hasattr(self.client, "_check_cancel"):
            self.client._check_cancel()

    def _build_doc_output_paths(self, current_dir: Path, safe_name: str, options: ExportOptions) -> DocOutputPaths:
        """构造单篇文档的输出路径集合。"""
        doc_dir = current_dir / safe_name
        ensure_dir(doc_dir)
        assets_dir = doc_dir / options.assets_dir_name
        raw_json_path = doc_dir / f"{safe_name}.yuque.json"
        raw_lake_path = doc_dir / f"{safe_name}.lake"
        return DocOutputPaths(
            doc_dir=doc_dir,
            markdown_path=doc_dir / f"{safe_name}.md",
            assets_dir=assets_dir,
            raw_json_path=raw_json_path,
            raw_lake_path=raw_lake_path,
        )

    def _mark_doc_completed(self, *, checkpoint: CheckpointState, doc_id: int | None, markdown_path: Path) -> None:
        """在断点信息中标记文档已成功导出。"""
        if doc_id and doc_id not in checkpoint.completed_doc_ids:
            checkpoint.completed_doc_ids.append(doc_id)
            checkpoint.doc_path_map[str(doc_id)] = str(markdown_path)
            checkpoint.last_success_doc_id = doc_id

    def _ensure_doc_state(self, checkpoint: CheckpointState, doc_id: int | None) -> DocExportState:
        """确保文档在断点状态中存在对应条目。"""
        key = str(doc_id or "unknown")
        state = checkpoint.doc_states.get(key)
        if state is None:
            state = DocExportState()
            checkpoint.doc_states[key] = state
        return state

    def _emit_progress(self, progress: ProgressSnapshot, **updates) -> None:
        """更新进度快照并通知外部回调。"""
        for key, value in updates.items():
            setattr(progress, key, value)
        rate_limit = getattr(self.client, "last_rate_limit", {}) or {}
        progress.rate_limit_limit = rate_limit.get("limit")
        progress.rate_limit_remaining = rate_limit.get("remaining")
        progress.rate_limit_reset = rate_limit.get("reset")

        if self.progress_callback is not None:
            self.progress_callback(progress)
        progress.new_warnings = []

    def _collect_doc_titles(self, nodes: list[TocNode], checkpoint: CheckpointState, options: ExportOptions) -> list[str]:
        """收集待导出文档标题，用于初始化进度预览。"""
        titles: list[str] = []
        for node in nodes:
            if node.node_type == "TITLE":
                titles.extend(self._collect_doc_titles(node.children, checkpoint, options))
                continue
            if node.node_type != "DOC":
                continue
            doc_id = node.doc_id
            if options.selected_doc_ids is not None and (not doc_id or doc_id not in options.selected_doc_ids):
                continue
            titles.append(node.title)
        if options.max_docs is not None:
            return titles[: options.max_docs]
        return titles

    def _advance_waiting_preview(self, progress: ProgressSnapshot, current_title: str) -> list[str]:
        """从等待预览中移除当前文档，并返回新的前几项。"""
        waiting_titles = progress.details.get("_waiting_titles", [])
        if isinstance(waiting_titles, list):
            try:
                waiting_titles.remove(current_title)
            except ValueError:
                # 当前标题可能已被提前移除，直接保持现状即可。
                pass
            return waiting_titles[:5]
        return [title for title in progress.waiting_preview if title != current_title][:5]

    def _push_recent(self, items: list[str], value: str, limit: int | None = None) -> list[str]:
        """向最近列表追加一项。"""
        if limit is None:
            queue = deque(items)
            queue.append(value)
            return list(queue)
        queue = deque(items, maxlen=limit)
        queue.append(value)
        return list(queue)

    def _build_repo_slug_map(self, repo_dir: Path, nodes: list[TocNode], docs_by_id: dict, current_dir: Path | None = None, used_names: dict[Path, set[str]] | None = None, selected_doc_ids: set[int] | None = None) -> dict[str, str]:
        """构建文档 slug 到路径的映射。

        说明:
            仅遍历实际会参与导出的目录，避免为未导出文档生成无意义映射。
        """
        current_dir = current_dir or repo_dir
        used_names = used_names or {}
        slug_map: dict[str, str] = {}
        name_pool = used_names.setdefault(current_dir, set())
        for node in nodes:
            safe_name = unique_name(sanitize_name(node.title), name_pool, suffix=str(node.doc_id) if node.doc_id else None)
            if node.node_type == "TITLE":
                has_selected_docs = self._has_selected_docs(node.children, selected_doc_ids)
                if has_selected_docs:
                    next_dir = current_dir / safe_name
                    slug_map.update(self._build_repo_slug_map(repo_dir, node.children, docs_by_id, next_dir, used_names, selected_doc_ids))
                continue
            if node.node_type != "DOC":
                continue
            if selected_doc_ids is not None and (not node.doc_id or node.doc_id not in selected_doc_ids):
                continue
            doc_meta = docs_by_id.get(node.doc_id) if node.doc_id else None
            doc_slug = node.slug or (doc_meta or {}).get("slug")
            if not doc_slug:
                continue
            doc_dir = current_dir / safe_name
            markdown_path = doc_dir / f"{safe_name}.md"
            slug_map[str(doc_slug)] = str(markdown_path)
        return slug_map

    def _has_selected_docs(self, nodes: list[TocNode], selected_doc_ids: set[int] | None) -> bool:
        """判断一组节点中是否包含待导出的文档。"""
        for node in nodes:
            if node.node_type == "TITLE":
                if self._has_selected_docs(node.children, selected_doc_ids):
                    return True
            elif node.node_type == "DOC":
                if selected_doc_ids is None:
                    return True
                if node.doc_id and node.doc_id in selected_doc_ids:
                    return True
        return False
