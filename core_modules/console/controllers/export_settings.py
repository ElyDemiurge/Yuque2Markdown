"""导出设置子菜单控制器。"""

from core_modules.console.helpers import parse_action, toggle_config_value
from core_modules.console.menu import MenuItem, run_menu
from core_modules.config.models import AppConfig, SessionState


class ExportSettingsController:
    """Controller for export settings menu operations."""

    def __init__(self, config: AppConfig, session: SessionState, *, status_lines_builder=None):
        self.config = config
        self.session = session
        self.status_lines_builder = status_lines_builder
        self.changed = False

    def run(self) -> bool:
        """Run the export settings menu and handle user interactions.

        Returns:
            bool: True if any settings were changed, False otherwise.
        """
        while True:
            items = self._build_menu_items()
            action = run_menu(
                "导出路径与资源",
                items,
                status_lines=self._build_status_lines(),
                initial_index=self.session.menu_index_map.get("export_settings", 0),
            )

            if action is None:
                return self.changed

            key, edited_value = parse_action(action)
            self._remember_menu_index(items, key)

            if key == "output_dir" and edited_value is not None:
                self._handle_output_dir(edited_value)
            elif key == "assets_dir_name" and edited_value is not None:
                self._handle_assets_dir(edited_value)
            elif key in {"resume", "strict", "offline_assets", "fail_on_asset_error"}:
                self._handle_toggle(key)

    def _build_menu_items(self) -> list[MenuItem]:
        """Build menu items for export settings."""
        return [
            MenuItem("section_paths", "── 路径与资源 ──", item_type="section", focusable=False),
            MenuItem("output_dir", "输出目录", self.config.export_defaults.output_dir, input_style=True),
            MenuItem("assets_dir_name", "资源目录名", self.config.export_defaults.assets_dir_name, input_style=True),
            MenuItem("section_flags", "── 导出行为 ──", item_type="section", focusable=False),
            MenuItem("resume", "断点续导", self._bool_text(self.config.export_defaults.resume), item_type="bool"),
            MenuItem("strict", "严格模式", self._bool_text(self.config.export_defaults.strict), item_type="bool"),
            MenuItem("offline_assets", "离线资源", self._bool_text(self.config.export_defaults.offline_assets), item_type="bool"),
            MenuItem("fail_on_asset_error", "资源下载失败时中止导出", self._bool_text(self.config.export_defaults.fail_on_asset_error), item_type="bool"),
        ]

    def _build_status_lines(self) -> list[str]:
        """Build status lines for submenu."""
        if self.status_lines_builder is not None:
            return self.status_lines_builder(self.config, self.session)
        return ["配置已保存" if not self.session.dirty else "有未保存的修改"]

    def _remember_menu_index(self, items: list[MenuItem], key: str) -> None:
        """Remember the menu index for the given action key."""
        for index, item in enumerate(items):
            if item.key == key:
                self.session.menu_index_map["export_settings"] = index
                return

    def _handle_output_dir(self, value: str) -> None:
        """Handle output directory setting change."""
        if value:
            self.config.export_defaults.output_dir = value
            self.session.status_message = "已更新输出目录"
            self.session.dirty = True
            self.changed = True

    def _handle_assets_dir(self, value: str) -> None:
        """Handle assets directory setting change."""
        if value:
            self.config.export_defaults.assets_dir_name = value
            self.session.status_message = "已更新资源目录名"
            self.session.dirty = True
            self.changed = True

    def _handle_toggle(self, key: str) -> None:
        """Handle boolean toggle setting change."""
        toggle_config_value(self.config, key)
        self.session.status_message = f"已更新: {key}"
        self.session.dirty = True
        self.changed = True

    def _bool_text(self, value: bool) -> str:
        """Convert boolean to Chinese text."""
        return "开启" if value else "关闭"
