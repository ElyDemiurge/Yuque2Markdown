"""运行与网络设置子菜单控制器。"""

from core_modules.console.helpers import (
    parse_action,
    parse_non_negative_float,
    parse_optional_positive_int,
    parse_positive_int,
    toggle_config_value,
)
from core_modules.console.menu import MenuItem, run_menu
from core_modules.config.models import AppConfig, SessionState


class RuntimeSettingsController:
    """管理“运行与网络设置”子菜单。"""

    def __init__(self, config: AppConfig, session: SessionState, *, status_lines_builder=None):
        self.config = config
        self.session = session
        self.status_lines_builder = status_lines_builder
        self.changed = False

    def run(self) -> bool:
        """运行“运行与网络设置”子菜单并处理交互。"""
        while True:
            items = self._build_menu_items()
            action = run_menu(
                "运行与网络设置",
                items,
                status_lines=self._build_status_lines(),
                initial_index=self.session.menu_index_map.get("runtime_settings", 0),
            )

            if action is None:
                return self.changed

            key, edited_value = parse_action(action)
            self._remember_menu_index(items, key)

            if key == "request_interval" and edited_value is not None:
                self._handle_request_interval(edited_value)
            elif key == "timeout" and edited_value is not None:
                self._handle_timeout(edited_value)
            elif key == "token_check_timeout" and edited_value is not None:
                self._handle_token_check_timeout(edited_value)
            elif key == "request_max_retries" and edited_value is not None:
                self._handle_request_max_retries(edited_value)
            elif key == "rate_limit_backoff_seconds" and edited_value is not None:
                self._handle_rate_limit_backoff(edited_value)
            elif key == "network_backoff_seconds" and edited_value is not None:
                self._handle_network_backoff(edited_value)
            elif key == "max_backoff_seconds" and edited_value is not None:
                self._handle_max_backoff(edited_value)
            elif key == "max_docs" and edited_value is not None:
                self._handle_max_docs(edited_value)
            elif key in {"confirm_before_export", "auto_save_after_export", "persist_token", "persist_cookie"}:
                self._handle_toggle(key)

    def _build_menu_items(self) -> list[MenuItem]:
        """构造运行设置菜单项。"""
        defaults = self.config.export_defaults

        return [
            MenuItem("section_network", "── 网络 ──", item_type="section", focusable=False),
            MenuItem("request_interval", "API 请求间隔", str(defaults.request_interval), input_style=True),
            MenuItem("timeout", "API 请求超时", f"{defaults.timeout}s", input_style=True, edit_value=str(defaults.timeout)),
            MenuItem("token_check_timeout", "检查 Token 可用性超时", f"{defaults.token_check_timeout}s", input_style=True, edit_value=str(defaults.token_check_timeout)),
            MenuItem("request_max_retries", "API 请求失败重试次数", str(defaults.request_max_retries), input_style=True),
            MenuItem("rate_limit_backoff_seconds", "触发限流后的首次等待时间", f"{defaults.rate_limit_backoff_seconds}s", input_style=True, edit_value=str(defaults.rate_limit_backoff_seconds)),
            MenuItem("network_backoff_seconds", "网络错误后的首次等待时间", f"{defaults.network_backoff_seconds}s", input_style=True, edit_value=str(defaults.network_backoff_seconds)),
            MenuItem("max_backoff_seconds", "单次重试等待上限", f"{defaults.max_backoff_seconds}s", input_style=True, edit_value=str(int(defaults.max_backoff_seconds))),
            MenuItem("max_docs", "最多导出文档数", "不限" if defaults.max_docs is None else str(defaults.max_docs), input_style=True, edit_value="" if defaults.max_docs is None else str(defaults.max_docs)),
            MenuItem("section_prefs", "── 偏好 ──", item_type="section", focusable=False),
            MenuItem("confirm_before_export", "导出前显示确认对话框", self._bool_text(self.config.ui_preferences.confirm_before_export), item_type="bool"),
            MenuItem("auto_save_after_export", "导出后自动保存配置", self._bool_text(self.config.ui_preferences.auto_save_after_export), item_type="bool"),
            MenuItem("persist_token", "保存 Token 到配置文件", self._bool_text(self.config.persist_token), item_type="bool"),
            MenuItem("persist_cookie", "保存 Cookie 到配置文件", self._bool_text(self.config.persist_cookie), item_type="bool"),
        ]

    def _build_status_lines(self) -> list[str]:
        """构造子菜单状态栏文本。"""
        if self.status_lines_builder is not None:
            return self.status_lines_builder(self.config, self.session)
        return ["配置已保存" if not self.session.dirty else "有未保存的修改"]

    def _remember_menu_index(self, items: list[MenuItem], key: str) -> None:
        """记住当前菜单光标位置。"""
        for index, item in enumerate(items):
            if item.key == key:
                self.session.menu_index_map["runtime_settings"] = index
                return

    def _handle_request_interval(self, value: str) -> None:
        """处理请求间隔修改。"""
        parsed = parse_non_negative_float(value)
        if parsed is not None:
            self.config.export_defaults.request_interval = parsed
            self.session.status_message = "已更新 API 请求间隔"
            self.session.dirty = True
            self.changed = True

    def _handle_timeout(self, value: str) -> None:
        """处理请求超时修改。"""
        parsed = parse_positive_int(value)
        if parsed is not None:
            self.config.export_defaults.timeout = parsed
            self.session.status_message = "已更新 API 请求超时"
            self.session.dirty = True
            self.changed = True

    def _handle_token_check_timeout(self, value: str) -> None:
        """处理 Token 检查超时修改。"""
        parsed = parse_positive_int(value)
        if parsed is not None:
            self.config.export_defaults.token_check_timeout = parsed
            self.session.status_message = "已更新检查 Token 可用性超时"
            self.session.dirty = True
            self.changed = True

    def _handle_request_max_retries(self, value: str) -> None:
        """处理请求重试次数修改。"""
        parsed = parse_positive_int(value)
        if parsed is not None:
            self.config.export_defaults.request_max_retries = parsed
            self.session.status_message = "已更新 API 请求失败重试次数"
            self.session.dirty = True
            self.changed = True

    def _handle_rate_limit_backoff(self, value: str) -> None:
        """处理触发限流后的首次等待时间修改。"""
        parsed = parse_non_negative_float(value)
        if parsed is not None:
            self.config.export_defaults.rate_limit_backoff_seconds = parsed
            self.session.status_message = "已更新触发限流后的首次等待时间"
            self.session.dirty = True
            self.changed = True

    def _handle_network_backoff(self, value: str) -> None:
        """处理网络错误后的首次等待时间修改。"""
        parsed = parse_non_negative_float(value)
        if parsed is not None:
            self.config.export_defaults.network_backoff_seconds = parsed
            self.session.status_message = "已更新网络错误后的首次等待时间"
            self.session.dirty = True
            self.changed = True

    def _handle_max_backoff(self, value: str) -> None:
        """处理单次重试等待上限修改。"""
        parsed = parse_positive_int(value)
        if parsed is not None:
            self.config.export_defaults.max_backoff_seconds = float(parsed)
            self.session.status_message = "已更新单次重试等待上限"
            self.session.dirty = True
            self.changed = True

    def _handle_max_docs(self, value: str) -> None:
        """处理最大导出文档数修改。"""
        parsed = parse_optional_positive_int(value)
        self.config.export_defaults.max_docs = parsed
        self.session.status_message = "已更新最多导出文档数"
        self.session.dirty = True
        self.changed = True

    def _handle_toggle(self, key: str) -> None:
        """处理布尔开关项切换。"""
        toggle_config_value(self.config, key)
        label_map = {
            "confirm_before_export": "导出前确认",
            "auto_save_after_export": "导出后自动保存配置",
            "persist_token": "保存 Token 到配置文件",
            "persist_cookie": "保存 Cookie 到配置文件",
        }
        self.session.status_message = f"已更新{label_map.get(key, key)}"
        self.session.dirty = True
        self.changed = True

    def _bool_text(self, value: bool) -> str:
        """将布尔值转为界面文案。"""
        return "开启" if value else "关闭"
