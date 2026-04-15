"""Tests for export settings controller attachment tree."""
import sys
sys.path.insert(0, ".")

from core_modules.config.models import AppConfig, SessionState
from core_modules.console.controllers.export_settings import ExportSettingsController


def test_attachment_section_contains_tree_structure():
    config = AppConfig()
    config.export_defaults.attachment_suffixes = [".zip"]
    controller = ExportSettingsController(config, SessionState())

    items = controller._build_menu_items()
    keys = [item.key for item in items]

    assert "section_attachments" in keys
    assert "attachment_suffixes_all" in keys
    assert "attachment_group__archives" in keys
    assert "attachment_row__archives__0" in keys
    assert "attachment_custom_suffixes" in keys
    assert keys.index("attachment_suffixes_all") < keys.index("attachment_group__archives") < keys.index("attachment_custom_suffixes")
    all_item = next(item for item in items if item.key == "attachment_suffixes_all")
    group_item = next(item for item in items if item.key == "attachment_group__archives")
    row_item = next(item for item in items if item.key == "attachment_row__archives__0")
    custom_item = next(item for item in items if item.key == "attachment_custom_suffixes")
    assert "无论是否启用，均默认下载 markdown 的图片资源" in all_item.title
    assert all_item.item_type == "readonly"
    assert all_item.value == "暂不可用"
    assert all_item.indent == 0
    assert group_item.indent == 1
    assert row_item.indent == 2
    assert custom_item.indent == 1
    assert group_item.item_type == "readonly"
    assert row_item.item_type == "readonly"
    assert custom_item.item_type == "readonly"
    assert custom_item.focusable is False
    row_item = next(item for item in items if item.key == "attachment_row__archives__0")
    assert len(row_item.inline_choices) == 3


def test_toggle_attachment_group_adds_all_suffixes():
    config = AppConfig()
    session = SessionState()
    controller = ExportSettingsController(config, session)

    controller._toggle_attachment_group("archives")

    assert config.export_defaults.attachment_suffixes == [".zip", ".rar", ".7z"]
    assert session.dirty is True
    assert controller.changed is True


def test_toggle_attachment_group_removes_all_suffixes_when_fully_selected():
    config = AppConfig()
    config.export_defaults.attachment_suffixes = [".zip", ".rar", ".7z", ".pdf"]
    controller = ExportSettingsController(config, SessionState())

    controller._toggle_attachment_group("archives")

    assert config.export_defaults.attachment_suffixes == [".pdf"]


def test_toggle_single_attachment_suffix():
    config = AppConfig()
    controller = ExportSettingsController(config, SessionState())

    controller._toggle_attachment_suffix(".pdf")
    assert config.export_defaults.attachment_suffixes == [".pdf"]

    controller._toggle_attachment_suffix(".pdf")
    assert config.export_defaults.attachment_suffixes == []


def test_all_resources_status_reflects_wildcard():
    config = AppConfig()
    config.export_defaults.attachment_suffixes = ["*"]
    controller = ExportSettingsController(config, SessionState())

    items = controller._build_menu_items()
    all_item = next(item for item in items if item.key == "attachment_suffixes_all")

    assert all_item.item_type == "readonly"
    assert all_item.value == "暂不可用"
    assert "attachment_group__archives" in [item.key for item in items]
