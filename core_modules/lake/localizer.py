from __future__ import annotations

import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from core_modules.export.file_naming import sanitize_name, unique_name
from core_modules.lake.models import MarkdownRenderResult, ResourceRef
from core_modules.lake.resource_parser import extract_yuque_doc_slug, is_yuque_doc_url
from core_modules.export.writer import write_binary_file


def localize_markdown_assets(
    render_result: MarkdownRenderResult,
    *,
    assets_dir: Path,
    fetch_binary,
    doc_slug_map: dict[str, str] | None = None,
    current_markdown_path: Path | None = None,
) -> MarkdownRenderResult:
    markdown = render_result.markdown
    warnings = list(render_result.warnings)

    if doc_slug_map and current_markdown_path is not None:
        markdown, rewritten = rewrite_doc_links(markdown, render_result.resources, doc_slug_map, current_markdown_path)
        if rewritten:
            warnings.append(f"已重写 {rewritten} 个内部文档链接")

    asset_resources = [resource for resource in render_result.resources if resource.kind in {"image", "attachment"}]
    if not asset_resources:
        return MarkdownRenderResult(markdown=markdown, resources=render_result.resources, warnings=warnings)

    assets_dir.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()
    localized_resources: list[ResourceRef] = []

    for resource in render_result.resources:
        if resource.kind not in {"image", "attachment"}:
            localized_resources.append(resource)
            continue

        new_resource = ResourceRef(
            original_url=resource.original_url,
            normalized_url=resource.normalized_url,
            kind=resource.kind,
            source_format=resource.source_format,
            alt_text=resource.alt_text,
            title=resource.title,
            local_path=resource.local_path,
            failed=resource.failed,
        )
        try:
            data = fetch_binary(resource.normalized_url)
            file_name = build_asset_name(resource, used_names)
            output_path = assets_dir / file_name
            write_binary_file(output_path, data)
            relative_path = f"./{assets_dir.name}/{file_name}"
            markdown = _replace_url_multi(markdown, resource, relative_path)
            new_resource.local_path = relative_path
        except Exception as exc:
            new_resource.failed = True
            warnings.append(f"资源下载失败: {resource.normalized_url} ({exc})")
        localized_resources.append(new_resource)

    return MarkdownRenderResult(markdown=markdown, resources=localized_resources, warnings=warnings)


def rewrite_doc_links(
    markdown: str,
    resources: list[ResourceRef],
    doc_slug_map: dict[str, str],
    current_markdown_path: Path,
) -> tuple[str, int]:
    rewritten = 0
    for resource in resources:
        if resource.kind != "doc":
            continue
        slug = extract_yuque_doc_slug(resource.normalized_url)
        if not slug:
            continue
        target_path = doc_slug_map.get(slug)
        if not target_path:
            continue
        relative_path = os.path.relpath(target_path, start=current_markdown_path.parent)
        # 同时替换 original_url 和 normalized_url（含 query/hash 变体）
        for url in _url_variants(resource.original_url, resource.normalized_url):
            if url in markdown:
                markdown = markdown.replace(url, relative_path)
                rewritten += 1
                break
    return markdown, rewritten


def _url_variants(original: str, normalized: str) -> list[str]:
    """生成同一资源的多个 URL 变体，覆盖带/不带 query/hash 的形式。"""
    variants: list[str] = []
    for url in (original, normalized):
        if url and url not in variants:
            variants.append(url)
        parsed = urlparse(url)
        # 去掉 query 和 fragment 再比较/替换
        base = parsed._replace(query="", fragment="").geturl()
        if base and base not in variants:
            variants.append(base)
        # 只有 query
        if parsed.query and f"{parsed.scheme}://{parsed.netloc}{parsed.path}" not in variants:
            base_no_query = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if base_no_query not in variants:
                variants.append(base_no_query)
    return variants


def _replace_url_multi(markdown: str, resource: ResourceRef, new_url: str) -> str:
    """用新 URL 替换资源在 Markdown 中出现的所有可能形式。"""
    for url in _url_variants(resource.original_url, resource.normalized_url):
        markdown = re.sub(re.escape(url), new_url, markdown)
    return markdown


def build_asset_name(resource: ResourceRef, used_names: set[str]) -> str:
    parsed = urlparse(resource.normalized_url)
    raw_name = Path(parsed.path).name or f"{resource.kind}"
    base_name = sanitize_name(Path(raw_name).stem or resource.kind, fallback=resource.kind)
    ext = Path(raw_name).suffix or guess_extension(resource)
    return unique_name(f"{base_name}{ext}", used_names)


def guess_extension(resource: ResourceRef) -> str:
    guessed, _ = mimetypes.guess_type(resource.normalized_url)
    if guessed:
        ext = mimetypes.guess_extension(guessed)
        if ext:
            return ext
    return ".bin" if resource.kind != "image" else ".img"


def replace_url(markdown: str, old_url: str, new_url: str) -> str:
    """保持向后兼容的单一 URL 替换。"""
    pattern = re.escape(old_url)
    return re.sub(pattern, new_url, markdown)
