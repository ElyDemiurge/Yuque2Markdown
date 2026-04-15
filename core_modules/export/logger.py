from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path


class ExportLogger:
    def __init__(self, log_path: Path) -> None:
        self._path = log_path
        self._start_time = time.monotonic()
        self._doc_start_time: float | None = None
        self._doc_titles: list[str] = []
        self._write_count: int = 0
        self._log_failures: int = 0
        self._last_error: str | None = None

    # ── 顶级事件 ──────────────────────────────────────────────

    def export_started(self, repo_name: str, output_dir: str, total_docs: int) -> None:
        self._write("INFO", f"导出开始 | 知识库: {repo_name} | 输出: {output_dir} | 文档总数: {total_docs}")

    def export_finished(
        self,
        exported: int,
        skipped: int,
        failed: int,
        warnings: int,
        resources_downloaded: int,
        resources_failed: int,
        rewritten_links: int,
    ) -> None:
        elapsed = self._elapsed()
        self._write("INFO", f"导出完成 | 成功: {exported} | 跳过: {skipped} | 失败: {failed} | "
            f"警告: {warnings} | 资源: 下载 {resources_downloaded} / 失败 {resources_failed} | "
            f"重写内部链接: {rewritten_links} | 耗时: {elapsed:.1f}s")

    def export_failed(self, reason: str) -> None:
        elapsed = self._elapsed()
        self._write("ERROR", f"导出失败 | {reason} | 耗时: {elapsed:.1f}s")

    # ── 文档级事件 ────────────────────────────────────────────

    def doc_started(self, title: str) -> None:
        self._doc_start_time = time.monotonic()
        self._doc_titles.append(title)
        self._write("INFO", f"[{len(self._doc_titles)}] 开始: {title}")

    def doc_markdown_done(self, title: str, warnings: int, resources: int) -> None:
        elapsed = self._doc_elapsed()
        self._write("INFO", f"[{len(self._doc_titles)}] Markdown 完成: {title} | "
            f"警告: {warnings} | 资源数: {resources} | 耗时: {elapsed:.1f}s")

    def doc_assets_done(self, title: str, downloaded: int, failed: int, rewritten: int) -> None:
        elapsed = self._doc_elapsed()
        parts = [f"[{len(self._doc_titles)}] 资源完成: {title}"]
        if downloaded > 0:
            parts.append(f"下载: {downloaded}")
        if failed > 0:
            parts.append(f"失败: {failed}")
        if rewritten > 0:
            parts.append(f"重写: {rewritten}")
        parts.append(f"耗时: {elapsed:.1f}s")
        self._write("INFO", " | ".join(parts))

    def doc_completed(self, title: str, warnings: int) -> None:
        elapsed = self._doc_elapsed()
        warn_str = f" | 警告: {warnings}" if warnings > 0 else ""
        self._write("INFO", f"[{len(self._doc_titles)}] 完成: {title}{warn_str} | 总耗时: {elapsed:.1f}s")

    def doc_skipped(self, title: str) -> None:
        self._write("INFO", f"[{len(self._doc_titles)}] 跳过: {title}")

    def doc_failed(self, title: str, reason: str) -> None:
        self._write("ERROR", f"[{len(self._doc_titles)}] 失败: {title} | {reason}")

    # ── 单条日志 ──────────────────────────────────────────────

    def warning(self, message: str) -> None:
        self._write("WARN", message)

    def error(self, message: str) -> None:
        self._write("ERROR", message)

    def info(self, message: str) -> None:
        self._write("INFO", message)

    def debug(self, message: str) -> None:
        self._write("DEBUG", message)

    # ── 内部 ──────────────────────────────────────────────────

    def _write(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        elapsed = self._elapsed()
        line = f"[{timestamp}] [{level:5s}] [T+{elapsed:8.1f}s] {message}"
        try:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            self._write_count += 1
        except OSError as exc:
            self._log_failures += 1
            self._last_error = str(exc)
            # 日志写入失败时尝试写入 stderr 作为 fallback
            import sys
            sys.stderr.write(f"[ExportLogger] 写入日志失败: {exc}\n")

    def get_status(self) -> dict:
        """获取日志状态，用于诊断。"""
        return {
            "path": str(self._path),
            "total_writes": self._write_count,
            "failures": self._log_failures,
            "last_error": self._last_error,
        }

    def _elapsed(self) -> float:
        return time.monotonic() - self._start_time

    def _doc_elapsed(self) -> float:
        if self._doc_start_time is None:
            return 0.0
        return time.monotonic() - self._doc_start_time
