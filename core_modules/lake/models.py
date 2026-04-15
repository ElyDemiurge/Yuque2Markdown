"""Lake 转换模块数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ResourceRef:
    """单个外部资源的引用记录。"""
    original_url: str
    normalized_url: str
    kind: str
    source_format: str
    alt_text: str | None = None
    title: str | None = None
    local_path: str | None = None
    failed: bool = False


@dataclass(slots=True)
class MarkdownRenderResult:
    """Lake 转 Markdown 的完整结果。"""
    markdown: str
    resources: list[ResourceRef] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rewritten_links: int = 0
