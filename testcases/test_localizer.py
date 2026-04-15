"""资源本地化测试。"""
import sys
sys.path.insert(0, ".")

from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

from core_modules.lake.localizer import (
    _url_variants,
    _replace_url_multi,
    localize_markdown_assets,
    rewrite_doc_links,
    build_asset_name,
    replace_url,
)
from core_modules.lake.models import MarkdownRenderResult, ResourceRef


def test_url_variants_original_and_normalized():
    v = _url_variants(
        "https://example.com/a.png?v=1#anchor",
        "https://example.com/a.png",
    )
    assert "https://example.com/a.png?v=1#anchor" in v
    assert "https://example.com/a.png" in v


def test_url_variants_dedup():
    v = _url_variants("https://a.com/x", "https://a.com/x")
    assert len([x for x in v if x == "https://a.com/x"]) == 1


def test_url_variants_base_without_query():
    v = _url_variants("https://cdn.yuque.com/1.png?v=2", "https://cdn.yuque.com/1.png?v=2")
    base = "https://cdn.yuque.com/1.png"
    assert base in v


def test_replace_url_multi_single():
    resource = ResourceRef(
        original_url="https://example.com/pic.png",
        normalized_url="https://example.com/pic.png",
        kind="image",
        source_format="lake",
    )
    md = "![图](https://example.com/pic.png)"
    result = _replace_url_multi(md, resource, "./assets/pic.png")
    assert "./assets/pic.png" in result
    assert "example.com" not in result


def test_replace_url_multi_with_query():
    resource = ResourceRef(
        original_url="https://example.com/pic.png?v=1",
        normalized_url="https://example.com/pic.png",
        kind="image",
        source_format="lake",
    )
    md = "![图](https://example.com/pic.png?v=1)"
    result = _replace_url_multi(md, resource, "./assets/pic.png")
    assert "./assets/pic.png" in result


def test_replace_url_multi_normalized_form():
    resource = ResourceRef(
        original_url="https://example.com/pic.png",
        normalized_url="https://example.com/pic.png",
        kind="image",
        source_format="lake",
    )
    md = "![图](https://example.com/pic.png)"
    result = _replace_url_multi(md, resource, "./assets/pic.png")
    assert "./assets/pic.png" in result


def test_localize_assets_replaces_markdown_url():
    render = MarkdownRenderResult(
        markdown="![图](https://example.com/pic.png)",
        resources=[
            ResourceRef(
                original_url="https://example.com/pic.png",
                normalized_url="https://example.com/pic.png",
                kind="image",
                source_format="lake",
            )
        ],
    )

    def fake_fetch(url):
        return b"fake-bytes"

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        assets_dir = Path(d) / "assets"
        result = localize_markdown_assets(
            render,
            assets_dir=assets_dir,
            fetch_binary=fake_fetch,
        )

    assert "./assets/" in result.markdown
    assert "example.com" not in result.markdown
    assert result.resources[0].local_path is not None
    assert result.resources[0].local_path.startswith("./assets/")
    assert result.warnings == []


def test_localize_assets_warns_on_failure():
    render = MarkdownRenderResult(
        markdown="![图](https://example.com/pic.png)",
        resources=[
            ResourceRef(
                original_url="https://example.com/pic.png",
                normalized_url="https://example.com/pic.png",
                kind="image",
                source_format="lake",
            )
        ],
    )

    def fake_fail(url):
        raise RuntimeError("boom")

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        assets_dir = Path(d) / "assets"
        result = localize_markdown_assets(
            render,
            assets_dir=assets_dir,
            fetch_binary=fake_fail,
        )

    assert any("下载失败" in w for w in result.warnings)
    assert result.resources[0].failed is True


def test_localize_assets_preserves_non_asset_resources():
    render = MarkdownRenderResult(
        markdown="[链接](https://example.com/page)",
        resources=[
            ResourceRef(
                original_url="https://example.com/page",
                normalized_url="https://example.com/page",
                kind="link",
                source_format="lake",
            )
        ],
    )

    def fake_fetch(url):
        return b"should-not-be-called"

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        assets_dir = Path(d) / "assets"
        result = localize_markdown_assets(
            render,
            assets_dir=assets_dir,
            fetch_binary=fake_fetch,
        )

    # link 不应被下载，markdown 保持不变
    assert "example.com/page" in result.markdown


def test_localize_attachment_keeps_link_and_warns_when_selected_suffix():
    render = MarkdownRenderResult(
        markdown="[附件](https://www.yuque.com/attachments/yuque/0/2022/pdf/demo.pdf)",
        resources=[
            ResourceRef(
                original_url="https://www.yuque.com/attachments/yuque/0/2022/pdf/demo.pdf",
                normalized_url="https://www.yuque.com/attachments/yuque/0/2022/pdf/demo.pdf",
                kind="attachment",
                source_format="lake",
                title="demo.pdf",
            )
        ],
    )

    def fake_fetch(url):
        raise AssertionError("attachment download should stay disabled")

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        assets_dir = Path(d) / "assets"
        result = localize_markdown_assets(
            render,
            assets_dir=assets_dir,
            fetch_binary=fake_fetch,
            attachment_suffixes=[".pdf"],
        )

    assert "https://www.yuque.com/attachments/yuque/0/2022/pdf/demo.pdf" in result.markdown
    assert result.resources[0].local_path is None
    assert any("暂不支持下载" in warning for warning in result.warnings)


def test_localize_attachment_keeps_unselected_suffix():
    render = MarkdownRenderResult(
        markdown="[附件](https://www.yuque.com/attachments/yuque/0/2022/docx/demo.docx)",
        resources=[
            ResourceRef(
                original_url="https://www.yuque.com/attachments/yuque/0/2022/docx/demo.docx",
                normalized_url="https://www.yuque.com/attachments/yuque/0/2022/docx/demo.docx",
                kind="attachment",
                source_format="lake",
                title="demo.docx",
            )
        ],
    )

    def fake_fetch(url):
        raise AssertionError("should not fetch unselected attachment type")

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        assets_dir = Path(d) / "assets"
        result = localize_markdown_assets(
            render,
            assets_dir=assets_dir,
            fetch_binary=fake_fetch,
            attachment_suffixes=[".pdf"],
        )

    assert "demo.docx" in result.markdown
    assert result.resources[0].local_path is None
    assert any("暂不支持下载" in warning for warning in result.warnings)


def test_localize_images_still_download_when_attachment_suffixes_empty():
    render = MarkdownRenderResult(
        markdown="![图](https://example.com/a.png)\n\n[附件](https://www.yuque.com/attachments/yuque/0/2022/zip/demo.zip)",
        resources=[
            ResourceRef(
                original_url="https://example.com/a.png",
                normalized_url="https://example.com/a.png",
                kind="image",
                source_format="lake",
            ),
            ResourceRef(
                original_url="https://www.yuque.com/attachments/yuque/0/2022/zip/demo.zip",
                normalized_url="https://www.yuque.com/attachments/yuque/0/2022/zip/demo.zip",
                kind="attachment",
                source_format="lake",
                title="demo.zip",
            ),
        ],
    )

    fetched: list[str] = []

    def fake_fetch(url):
        fetched.append(url)
        return b"bytes"

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        assets_dir = Path(d) / "assets"
        result = localize_markdown_assets(
            render,
            assets_dir=assets_dir,
            fetch_binary=fake_fetch,
            attachment_suffixes=[],
        )

    assert fetched == ["https://example.com/a.png"]
    assert result.resources[0].local_path is not None
    assert result.resources[1].local_path is None


def test_yuque_attachment_url_not_classified_as_doc():
    render = MarkdownRenderResult(
        markdown="[附件](https://www.yuque.com/attachments/yuque/0/2022/pdf/demo.pdf)",
        resources=[],
    )
    from core_modules.lake.resource_parser import collect_resources

    resources = collect_resources(render.markdown, "lake")
    assert resources[0].kind == "attachment"


def test_rewrite_doc_links_finds_target():
    render = MarkdownRenderResult(
        markdown="[文档](https://www.yuque.com/cyberangel/rg9gdm/doc-2)",
        resources=[
            ResourceRef(
                original_url="https://www.yuque.com/cyberangel/rg9gdm/doc-2",
                normalized_url="https://www.yuque.com/cyberangel/rg9gdm/doc-2",
                kind="doc",
                source_format="lake",
            )
        ],
    )
    slug_map = {"doc-2": "/output/test/文档2/文档2.md"}
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        md_path = Path(d) / "文档1.md"
        md_path.touch()
        result_md, count = rewrite_doc_links(
            render.markdown, render.resources, slug_map, md_path
        )

    assert count == 1
    assert "yuque.com" not in result_md


def test_rewrite_doc_links_missing_target_no_crash():
    render = MarkdownRenderResult(
        markdown="[文档](https://www.yuque.com/cyberangel/rg9gdm/missing)",
        resources=[
            ResourceRef(
                original_url="https://www.yuque.com/cyberangel/rg9gdm/missing",
                normalized_url="https://www.yuque.com/cyberangel/rg9gdm/missing",
                kind="doc",
                source_format="lake",
            )
        ],
    )
    slug_map = {}  # 目标不存在
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        md_path = Path(d) / "文档1.md"
        md_path.touch()
        result_md, count = rewrite_doc_links(
            render.markdown, render.resources, slug_map, md_path
        )

    # 不崩溃，原始 URL 保持不变
    assert count == 0
    assert "yuque.com" in result_md


def test_rewrite_doc_links_with_query():
    render = MarkdownRenderResult(
        markdown="[文档](https://www.yuque.com/cyberangel/rg9gdm/doc-2?from=link)",
        resources=[
            ResourceRef(
                original_url="https://www.yuque.com/cyberangel/rg9gdm/doc-2?from=link",
                normalized_url="https://www.yuque.com/cyberangel/rg9gdm/doc-2",
                kind="doc",
                source_format="lake",
            )
        ],
    )
    slug_map = {"doc-2": "/output/test/文档2/文档2.md"}
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        md_path = Path(d) / "文档1.md"
        md_path.touch()
        result_md, count = rewrite_doc_links(
            render.markdown, render.resources, slug_map, md_path
        )

    assert count == 1
    assert "yuque.com" not in result_md


def test_build_asset_name_handles_empty_path():
    resource = ResourceRef(
        original_url="https://example.com/",
        normalized_url="https://example.com/",
        kind="image",
        source_format="lake",
    )
    name = build_asset_name(resource, set())
    assert name
    assert "." in name


def test_replace_url_backward_compat():
    md = "![图](https://example.com/pic.png)"
    result = replace_url(md, "https://example.com/pic.png", "./assets/pic.png")
    assert result == "![图](./assets/pic.png)"
