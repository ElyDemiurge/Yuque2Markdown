"""导出设置控制器中的附件树测试。"""
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
    assert "attachment_disabled" in keys
    assert "attachment_suffixes_all" not in keys
    disabled_item = next(item for item in items if item.key == "attachment_disabled")
    assert disabled_item.title == "[-] 附件下载"
    assert disabled_item.item_type == "readonly"
    assert disabled_item.value.startswith("使用 Token 登录时无法下载附件")


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
    disabled_item = next(item for item in items if item.key == "attachment_disabled")

    assert disabled_item.title == "[-] 附件下载"
    assert disabled_item.item_type == "readonly"
    assert disabled_item.value.startswith("使用 Token 登录时无法下载附件")
    assert "attachment_group__archives" not in [item.key for item in items]


def test_attachment_section_enabled_with_cookie_login():
    config = AppConfig(auth_mode="cookie", cookie="yuque_ctoken=demo")
    config.export_defaults.attachment_suffixes = ["*"]
    controller = ExportSettingsController(config, SessionState())

    items = controller._build_menu_items()
    all_item = next(item for item in items if item.key == "attachment_suffixes_all")
    group_item = next(item for item in items if item.key == "attachment_group__archives")

    assert all_item.item_type == "check"
    assert all_item.focusable is True
    assert all_item.value == "开启"
    assert group_item.item_type == "check"
    assert group_item.focusable is True
    assert group_item.value == "开启"
