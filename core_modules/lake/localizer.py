from __future__ import annotations

import mimetypes
import os
import re
from zipfile import BadZipFile, ZipFile
from pathlib import Path
from urllib.parse import urlparse

from core_modules.config.models import normalize_attachment_suffixes
from core_modules.export.file_naming import sanitize_name, unique_name
from core_modules.export.writer import write_binary_file
from core_modules.lake.models import MarkdownRenderResult, ResourceRef
from core_modules.lake.resource_parser import extract_yuque_doc_slug

YUQUE_ATTACHMENT_UNSUPPORTED_TEMPLATE = "发现 {count} 个语雀附件链接，官方 API 暂不支持下载，已保留原始链接"


def localize_markdown_assets(
    render_result: MarkdownRenderResult,
    *,
    assets_dir: Path,
    fetch_binary=None,
    doc_slug_map: dict[str, str] | None = None,
    current_markdown_path: Path | None = None,
    attachment_suffixes: list[str] | None = None,
) -> MarkdownRenderResult:
    markdown = render_result.markdown
    warnings = list(render_result.warnings)
    rewritten = 0
    # `attachment_suffixes` 相关逻辑继续保留，等语雀官方补齐附件接口后可直接恢复使用。
    normalized_suffixes = normalize_attachment_suffixes(attachment_suffixes)
    attachment_resources = [resource for resource in render_result.resources if resource.kind == "attachment"]

    if doc_slug_map and current_markdown_path is not None:
        markdown, rewritten = rewrite_doc_links(markdown, render_result.resources, doc_slug_map, current_markdown_path)

    if attachment_resources:
        warnings.append(YUQUE_ATTACHMENT_UNSUPPORTED_TEMPLATE.format(count=len(attachment_resources)))

    asset_resources = [resource for resource in render_result.resources if resource.kind in {"image", "attachment"}]
    if not asset_resources:
        return MarkdownRenderResult(
            markdown=markdown,
            resources=render_result.resources,
            warnings=warnings,
            rewritten_links=rewritten,
        )

    assets_dir.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()
    localized_resources: list[ResourceRef] = []

    for resource in render_result.resources:
        if resource.kind not in {"image", "attachment"}:
            localized_resources.append(resource)
            continue

        if not _should_download_resource(resource, normalized_suffixes):
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
            file_name = build_asset_name(resource, used_names)
            output_path = assets_dir / file_name
            relative_path = f"./{assets_dir.name}/{file_name}"
            if output_path.exists():
                if _is_valid_existing_asset(output_path):
                    markdown = _replace_url_multi(markdown, resource, relative_path)
                    new_resource.local_path = relative_path
                    localized_resources.append(new_resource)
                    continue
                output_path.unlink(missing_ok=True)
            if fetch_binary is None:
                localized_resources.append(new_resource)
                continue
            data = fetch_binary(resource.normalized_url)
            write_binary_file(output_path, data)
            markdown = _replace_url_multi(markdown, resource, relative_path)
            new_resource.local_path = relative_path
        except Exception as exc:
            new_resource.failed = True
            warnings.append(f"资源下载失败: {resource.normalized_url} ({exc})")
        localized_resources.append(new_resource)

    return MarkdownRenderResult(
        markdown=markdown,
        resources=localized_resources,
        warnings=warnings,
        rewritten_links=rewritten,
    )


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


def _should_download_resource(resource: ResourceRef, attachment_suffixes: list[str]) -> bool:
    """决定资源是否需要下载到本地。"""
    if resource.kind == "image":
        return True
    if resource.kind != "attachment":
        return False
    # 当前阶段仅本地化图片，附件仍保留语雀原始链接。
    # 参数继续保留，避免未来恢复附件下载时再改外部调用链。
    return False


def _resource_suffix_candidates(resource: ResourceRef) -> list[str]:
    """提取资源可能的扩展名候选。"""
    candidates: list[str] = []
    for raw in (resource.normalized_url, resource.title or "", resource.alt_text or ""):
        suffix = Path(urlparse(raw).path or raw).suffix.lower()
        if suffix and suffix not in candidates:
            candidates.append(suffix)
    return candidates


def _is_valid_existing_asset(path: Path) -> bool:
    """判断已存在本地资源是否可信，避免复用误下载的 HTML 页面。"""
    try:
        data = path.read_bytes()
    except OSError:
        return False
    if _looks_like_html_file(data):
        return False
    suffix = path.suffix.lower()
    if suffix in {".docx", ".xlsx", ".pptx", ".zip"}:
        return _is_valid_zip_file(path)
    if suffix == ".pdf":
        return data.startswith(b"%PDF-")
    if suffix == ".7z":
        return data.startswith(b"7z\xbc\xaf\x27\x1c")
    if suffix == ".rar":
        return data.startswith(b"Rar!")
    return True


def _looks_like_html_file(data: bytes) -> bool:
    prefix = data[:256].lstrip().lower()
    return prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html")


def _is_valid_zip_file(path: Path) -> bool:
    try:
        with ZipFile(path) as archive:
            return archive.testzip() is None
    except (BadZipFile, OSError):
        return False
