"""导出与根据 .lake 重新生成 Markdown 的共用流程测试。"""

import sys
import json
from urllib.parse import quote
from pathlib import Path

sys.path.insert(0, ".")

from core_modules.export.exporter import build_doc_markdown_result
import regenerate_md


def _file_card_lake(url: str, name: str) -> str:
    payload = quote(json.dumps({"src": url, "name": name}, ensure_ascii=False))
    return f'<card type="inline" name="file" value="data:{payload}"/>'


def test_build_doc_markdown_result_keeps_attachment_link_even_if_local_asset_exists(tmp_path: Path) -> None:
    doc_dir = tmp_path / "Doc"
    assets_dir = doc_dir / "assets"
    assets_dir.mkdir(parents=True)
    existing = assets_dir / "demo.pdf"
    existing.write_bytes(b"pdf")
    markdown_path = doc_dir / "Doc.md"

    doc_data = {
        "title": "Doc",
        "body": "[附件](https://www.yuque.com/attachments/yuque/0/2022/pdf/demo.pdf)",
    }

    result = build_doc_markdown_result(
        doc_data,
        markdown_path=markdown_path,
        assets_dir=assets_dir,
        offline_assets=True,
        attachment_suffixes=[".pdf"],
        fetch_binary=None,
        doc_slug_map=None,
    )

    assert "https://www.yuque.com/attachments/yuque/0/2022/pdf/demo.pdf" in result.markdown


def test_build_doc_markdown_result_rewrites_existing_internal_doc_link(tmp_path: Path) -> None:
    src_dir = tmp_path / "A"
    dst_dir = tmp_path / "B"
    src_dir.mkdir(parents=True)
    dst_dir.mkdir(parents=True)
    markdown_path = src_dir / "A.md"
    target_path = dst_dir / "B.md"
    target_path.write_text("# B\n", encoding="utf-8")

    doc_data = {
        "title": "A",
        "body": "[跳转](https://www.yuque.com/cyberangel/demo/doc-b)",
    }

    result = build_doc_markdown_result(
        doc_data,
        markdown_path=markdown_path,
        assets_dir=src_dir / "assets",
        offline_assets=True,
        attachment_suffixes=[],
        fetch_binary=None,
        doc_slug_map={"doc-b": str(target_path)},
    )

    assert "../B/B.md" in result.markdown


def test_regenerate_all_keeps_attachment_link_without_downloading(tmp_path: Path, monkeypatch) -> None:
    output_root = tmp_path / "output"
    doc_dir = output_root / "Repo" / "Doc"
    doc_dir.mkdir(parents=True)
    lake_file = doc_dir / "Doc.lake"
    json_file = doc_dir / "Doc.yuque.json"
    md_file = doc_dir / "Doc.md"

    attachment_url = "https://www.yuque.com/attachments/yuque/0/2022/pdf/demo.pdf"
    lake_file.write_text(_file_card_lake(attachment_url, "demo.pdf"), encoding="utf-8")
    json_file.write_text(json.dumps({"data": {"title": "Doc", "slug": "doc"}}), encoding="utf-8")

    class DummyClient:
        def fetch_binary(self, url: str) -> bytes:
            raise AssertionError("attachment download should stay disabled")

    class DummyConfig:
        def __init__(self):
            from core_modules.config.models import AppConfig

            self._config = AppConfig()
            self._config.token = "demo-token"
            self._config.export_defaults.output_dir = str(output_root)
            self._config.export_defaults.attachment_suffixes = [".pdf"]
            self._config.export_defaults.offline_assets = True

        def __getattr__(self, name):
            return getattr(self._config, name)

    monkeypatch.setattr(regenerate_md, "load_config", lambda: DummyConfig())
    monkeypatch.setattr(regenerate_md, "_build_regenerate_client", lambda config: DummyClient())

    assert regenerate_md.regenerate_all() == 0
    content = md_file.read_text(encoding="utf-8")
    assert attachment_url in content
    assert not (doc_dir / "assets" / "demo.pdf").exists()


def test_regenerate_all_keeps_attachment_link_even_if_local_asset_exists(tmp_path: Path, monkeypatch) -> None:
    output_root = tmp_path / "output"
    doc_dir = output_root / "Repo" / "Doc"
    assets_dir = doc_dir / "assets"
    assets_dir.mkdir(parents=True)
    lake_file = doc_dir / "Doc.lake"
    json_file = doc_dir / "Doc.yuque.json"
    md_file = doc_dir / "Doc.md"
    existing_asset = assets_dir / "demo.pdf"
    existing_asset.write_bytes(b"pdf")

    attachment_url = "https://www.yuque.com/attachments/yuque/0/2022/pdf/demo.pdf"
    lake_file.write_text(_file_card_lake(attachment_url, "demo.pdf"), encoding="utf-8")
    json_file.write_text(json.dumps({"data": {"title": "Doc", "slug": "doc"}}), encoding="utf-8")

    class DummyConfig:
        def __init__(self):
            from core_modules.config.models import AppConfig

            self._config = AppConfig()
            self._config.export_defaults.output_dir = str(output_root)
            self._config.export_defaults.attachment_suffixes = [".pdf"]
            self._config.export_defaults.offline_assets = True

        def __getattr__(self, name):
            return getattr(self._config, name)

    monkeypatch.setattr(regenerate_md, "load_config", lambda: DummyConfig())
    monkeypatch.setattr(regenerate_md, "_build_regenerate_client", lambda config: None)

    assert regenerate_md.regenerate_all() == 0
    content = md_file.read_text(encoding="utf-8")
    assert attachment_url in content
    assert existing_asset.exists()


def test_regenerate_all_writes_empty_lake_file_for_empty_lake_doc(tmp_path: Path, monkeypatch) -> None:
    output_root = tmp_path / "output"
    doc_dir = output_root / "Repo" / "Doc"
    doc_dir.mkdir(parents=True)
    json_file = doc_dir / "Doc.yuque.json"
    md_file = doc_dir / "Doc.md"
    lake_file = doc_dir / "Doc.lake"
    lake_file.write_text("", encoding="utf-8")
    json_file.write_text(json.dumps({"data": {"title": "Doc", "slug": "doc", "format": "lake", "body_lake": ""}}), encoding="utf-8")

    class DummyClient:
        def fetch_binary(self, url: str) -> bytes:
            raise AssertionError("should not fetch")

    class DummyConfig:
        def __init__(self):
            from core_modules.config.models import AppConfig

            self._config = AppConfig()
            self._config.export_defaults.output_dir = str(output_root)
            self._config.export_defaults.offline_assets = True

        def __getattr__(self, name):
            return getattr(self._config, name)

    monkeypatch.setattr(regenerate_md, "load_config", lambda: DummyConfig())
    monkeypatch.setattr(regenerate_md, "_build_regenerate_client", lambda config: DummyClient())
    monkeypatch.setattr(regenerate_md, "_collect_doc_entries", lambda output_root: [(lake_file, json_file, md_file)])

    assert regenerate_md.regenerate_all() == 0
    assert lake_file.exists()
    assert lake_file.read_text(encoding="utf-8") == ""
