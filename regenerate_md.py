#!/usr/bin/env python3
"""根据已导出的 .lake 文件重新生成 Markdown，并按配置补齐本地资源。"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from core_modules.config.models import summarize_attachment_suffixes
from core_modules.config.models import normalize_auth_mode, AUTH_MODE_COOKIE
from core_modules.config.store import load_config
from core_modules.export.cli import build_client
from core_modules.export.exporter import build_doc_markdown_result
from core_modules.version import APP_VERSION


logger = logging.getLogger(__name__)


def _configure_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] [%(message)s]",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def _collect_doc_entries(output_root: Path) -> list[tuple[Path, Path | None, Path]]:
    entries: list[tuple[Path, Path | None, Path]] = []
    for lake_file in sorted(output_root.rglob("*.lake")):
        doc_dir = lake_file.parent
        stem = lake_file.stem
        json_file = doc_dir / f"{stem}.yuque.json"
        md_file = doc_dir / f"{stem}.md"
        entries.append((lake_file, json_file if json_file.exists() else None, md_file))
    return entries


def _build_regenerate_client(config):
    """按现有配置构建语雀客户端，主要用于补充下载缺失图片。"""
    auth_mode = normalize_auth_mode(config.auth_mode)
    token = (config.token or "").strip()
    cookie = (config.cookie or "").strip()
    if auth_mode == AUTH_MODE_COOKIE and not cookie:
        return None
    if auth_mode != AUTH_MODE_COOKIE and not token:
        return None
    defaults = config.export_defaults
    proxy = defaults.proxy
    proxy_host = proxy.host or None if proxy.enabled else None
    return build_client(
        token,
        cookie=cookie,
        auth_mode=auth_mode,
        request_interval=defaults.request_interval,
        timeout=defaults.timeout,
        max_retries=defaults.request_max_retries,
        rate_limit_backoff_seconds=defaults.rate_limit_backoff_seconds,
        network_backoff_seconds=defaults.network_backoff_seconds,
        max_backoff_seconds=defaults.max_backoff_seconds,
        proxy_host=proxy_host,
        proxy_port=proxy.port,
        proxy_test_url=proxy.test_url,
    )


def _build_doc_slug_map(entries: list[tuple[Path, Path | None, Path]]) -> dict[str, str]:
    slug_map: dict[str, str] = {}
    for _lake_file, json_file, md_file in entries:
        if json_file is None:
            continue
        try:
            raw = json.loads(json_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        doc_data = raw.get("data", raw)
        slug = str(doc_data.get("slug") or "").strip()
        if slug:
            slug_map[slug] = str(md_file)
    return slug_map


def regenerate_all() -> int:
    config = load_config()
    output_root = Path(config.export_defaults.output_dir)
    log_file = output_root / "regenerate.log"
    _configure_logging(log_file)
    client = _build_regenerate_client(config)

    entries = _collect_doc_entries(output_root)
    if not entries:
        logger.warning(f"未在 {output_root} 找到可用于重新生成 Markdown 的 .lake 文件")
        return 1
    doc_slug_map = _build_doc_slug_map(entries)

    logger.info(
        "开始根据 .lake 重新生成 Markdown | 版本: %s | 文档数: %s | 输出目录: %s | 附件处理: %s | 输入来源: .lake",
        APP_VERSION,
        len(entries),
        output_root,
        summarize_attachment_suffixes(config.export_defaults.attachment_suffixes),
    )

    converted = 0
    failed = 0
    total_warnings = 0

    for index, (lake_file, json_file, md_file) in enumerate(entries, 1):
        try:
            if json_file is not None:
                raw = json.loads(json_file.read_text(encoding="utf-8"))
                doc_data = raw.get("data", raw)
            else:
                doc_data = {}
            doc_data = dict(doc_data)
            doc_data["title"] = doc_data.get("title") or md_file.stem
            doc_data["body_lake"] = lake_file.read_text(encoding="utf-8")
            title = doc_data["title"]

            # 先复用本地 assets 并改写链接；本地缺失且有 Token 时再补充下载图片。
            # 语雀附件链接仍保留远程地址，重新生成 Markdown 时不会下载。
            result = build_doc_markdown_result(
                doc_data,
                markdown_path=md_file,
                assets_dir=md_file.parent / config.export_defaults.assets_dir_name,
                offline_assets=config.export_defaults.offline_assets,
                attachment_suffixes=config.export_defaults.attachment_suffixes,
                allow_attachment_downloads=normalize_auth_mode(config.auth_mode) == AUTH_MODE_COOKIE,
                fetch_binary=client.fetch_binary if client is not None else None,
                doc_slug_map=doc_slug_map,
            )

            md_file.write_text(result.markdown, encoding="utf-8")
            converted += 1
            total_warnings += len(result.warnings)

            if result.warnings:
                logger.warning("[%s/%s] %s | 警告数: %s", index, len(entries), title, len(result.warnings))
                for warning in result.warnings:
                    logger.warning("  - %s", warning)
            else:
                logger.info("[%s/%s] %s | 转换成功", index, len(entries), title)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.error("[%s/%s] 根据 .lake 重新生成 Markdown 失败: %s | %s", index, len(entries), md_file.stem, exc)

    logger.info("根据 .lake 重新生成 Markdown 完成 | 成功: %s | 失败: %s | 总警告: %s", converted, failed, total_warnings)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(regenerate_all())
