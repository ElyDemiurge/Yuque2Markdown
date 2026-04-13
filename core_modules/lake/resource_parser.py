"""从 Markdown 中提取外部资源（图片、附件、链接）。"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from core_modules.lake.models import ResourceRef

_MARKDOWN_IMAGE_PATTERN = re.compile(r'!\[(?P<alt>[^\]]*)\]\((?P<url>[^)\s]+)(?:\s+"(?P<title>[^"]*)")?\)')
_MARKDOWN_LINK_PATTERN = re.compile(r'(?<!!)\[(?P<text>[^\]]+)\]\((?P<url>[^)\s]+)(?:\s+"(?P<title>[^"]*)")?\)')
_HTML_ATTR_PATTERN = re.compile(r'(?P<attr>src|href)\s*=\s*["\'](?P<url>[^"\']+)["\']', re.I)
_URL_PATTERN = re.compile(r'https?://[^\s)"\']+')
# 匹配语雀文档 URL，支持 query string 和 hash 片段
_YUQUE_DOC_PATTERN = re.compile(
    r"https?://(?:www\.)?yuque\.com/(?P<group>[^/]+)/(?P<book>[^/]+)/(?P<slug>[^/\s)#?]+)"
)
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}


def normalize_resource_url(url: str, base_url: str | None = None) -> str:
    """规范化 URL：处理协议省略、相对路径等。"""
    raw = url.strip()
    if not raw:
        return raw
    if raw.startswith("//"):
        return f"https:{raw}"
    if base_url and not urlparse(raw).scheme and raw.startswith("/"):
        return urljoin(base_url, raw)
    return raw


def is_remote_url(url: str) -> bool:
    """判断是否为远程 HTTP/HTTPS URL。"""
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"}


def collect_resources(markdown: str, source_format: str, base_url: str | None = None) -> list[ResourceRef]:
    """从 Markdown 中提取所有外部资源，按类型分类。"""
    resources: list[ResourceRef] = []
    seen: set[str] = set()

    def add(url: str, kind: str, alt_text: str | None = None, title: str | None = None) -> None:
        normalized = normalize_resource_url(url, base_url=base_url)
        if not normalized or not is_remote_url(normalized) or normalized in seen:
            return
        seen.add(normalized)
        resources.append(
            ResourceRef(
                original_url=url,
                normalized_url=normalized,
                kind=kind,
                source_format=source_format,
                alt_text=alt_text,
                title=title,
            )
        )

    for match in _MARKDOWN_IMAGE_PATTERN.finditer(markdown):
        add(match.group("url"), "image", alt_text=match.group("alt") or None, title=match.group("title") or None)

    for match in _MARKDOWN_LINK_PATTERN.finditer(markdown):
        url = match.group("url")
        if is_yuque_doc_url(url):
            kind = "doc"
        elif is_attachment_url(url):
            kind = "attachment"
        else:
            kind = "link"
        add(url, kind, alt_text=match.group("text") or None, title=match.group("title") or None)

    for match in _HTML_ATTR_PATTERN.finditer(markdown):
        attr = match.group("attr").lower()
        url = match.group("url")
        if attr == "src":
            kind = "image" if is_image_url(url) else "attachment"
        elif is_yuque_doc_url(url):
            kind = "doc"
        elif is_attachment_url(url):
            kind = "attachment"
        else:
            kind = "link"
        add(url, kind)

    if source_format == "lake":
        for match in _URL_PATTERN.finditer(markdown):
            url = match.group(0)
            if is_yuque_doc_url(url):
                kind = "doc"
            elif is_attachment_url(url):
                kind = "attachment"
            else:
                kind = "link"
            add(url, kind)

    return resources


def is_yuque_doc_url(url: str) -> bool:
    """判断 URL 是否为语雀文档链接。"""
    return _YUQUE_DOC_PATTERN.match(url.strip()) is not None


def extract_yuque_doc_slug(url: str) -> str | None:
    """从语雀文档 URL 中提取 slug。"""
    match = _YUQUE_DOC_PATTERN.match(url.strip())
    if not match:
        return None
    return match.group("slug")


def is_image_url(url: str) -> bool:
    """根据 URL 路径判断是否为图片。"""
    path = urlparse(url.strip()).path.lower()
    return any(path.endswith(ext) for ext in _IMAGE_EXTENSIONS)


def is_attachment_url(url: str) -> bool:
    """判断是否为语雀 CDN 上的附件 URL，应下载到本地。

    仅匹配附件上传路径（/attachments/、含 /2022/pdf/ 等时间戳路径）或明确的
    CDN 域名（www.nlark.com/yuque/、yuqueusercontent.com、aliyuncs.com），
    不匹配普通语雀文档页面链接。
    """
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    path = parsed.path.lower()

    # 明确匹配附件 CDN 域名
    if "yuqueusercontent.com" in host or "aliyuncs.com" in host or "cdn.nlark.com" in host:
        return True

    # www.yuque.com / yuque.com 域名下：仅匹配 attachments 路径或含时间戳路径的附件
    if "yuque.com" in host:
        # 附件上传路径：/attachments/ 或 /0/<year>/<type>/ 格式（<type> 为 pdf/zip 等）
        if "/attachments/" in path:
            return True
        # 时间戳格式路径：/0/<year>/<type>/（如 /0/2022/pdf/574026/xxx.pdf）
        if re.search(r"/0/\d{4}/(pdf|zip|doc|docx|xls|xlsx|png|jpg|jpeg|gif|webp)/", path):
            return True

    return False
