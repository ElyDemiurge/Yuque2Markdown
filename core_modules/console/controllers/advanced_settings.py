"""网络与代理子菜单控制器。"""

from core_modules.console.helpers import parse_action
from core_modules.config.models import AppConfig, SessionState
from core_modules.console.menu import MenuItem, run_menu, show_message


class AdvancedSettingsController:
    """管理“网络与代理”子菜单。"""

    def __init__(self, config: AppConfig, session: SessionState, *, build_client_from_config, status_lines_builder=None):
        self.config = config
        self.session = session
        self.build_client_from_config = build_client_from_config
        self.status_lines_builder = status_lines_builder
        self.changed = False

    def run(self) -> bool:
        """运行“网络与代理”子菜单。"""
        while True:
            items = self._build_menu_items()
            action = run_menu(
                "网络与代理",
                items,
                status_lines=self._build_status_lines(),
                initial_index=self.session.menu_index_map.get("advanced_settings", 0),
            )
            if action is None:
                return self.changed
            key, edited_value = parse_action(action)
            self._remember_menu_index(items, key)
            proxy = self.config.export_defaults.proxy
            if key == "proxy_enabled":
                proxy.enabled = not proxy.enabled
                self._mark_network_config_changed()
            elif key == "proxy_host" and edited_value is not None:
                proxy.host = edited_value.strip()
                self._mark_network_config_changed()
            elif key == "proxy_port" and edited_value is not None:
                try:
                    port = int(edited_value.strip())
                except ValueError:
                    show_message("端口无效", ["请输入有效的端口号"])
                    continue
                if 1 <= port <= 65535:
                    proxy.port = port
                    self._mark_network_config_changed()
                else:
                    show_message("端口无效", ["端口必须在 1-65535 范围内"])
            elif key == "proxy_test_url" and edited_value is not None:
                url = edited_value.strip()
                if url and (url.startswith("http://") or url.startswith("https://")):
                    proxy.test_url = url
                    self._mark_network_config_changed()
                else:
                    show_message("地址无效", ["请输入有效的 HTTP/HTTPS 地址"])
            elif key == "test_proxy":
                self._handle_test_proxy()
            elif key == "test_direct_connection":
                self._handle_test_direct_connection()

    def _build_menu_items(self) -> list[MenuItem]:
        """构造“网络与代理”子菜单项。"""
        proxy = self.config.export_defaults.proxy
        items: list[MenuItem] = [
            MenuItem("section_proxy", "── 本地代理 ──", item_type="section", focusable=False),
            MenuItem("proxy_enabled", "代理", "开启" if proxy.enabled else "关闭", item_type="bool"),
        ]
        if proxy.enabled:
            port_display = str(proxy.port) if proxy.host else "未设置"
            items.extend(
                [
                    MenuItem("proxy_host", "代理地址", proxy.host or "未设置", input_style=True, edit_value=proxy.host or "", indent=1),
                    MenuItem("proxy_port", "代理端口", port_display, input_style=True, edit_value=str(proxy.port), indent=1),
                    MenuItem("proxy_test_url", "代理测试地址", proxy.test_url, input_style=True, edit_value=proxy.test_url, indent=1),
                    MenuItem("test_proxy", "测试代理", item_type="action", indent=1),
                ]
            )
        items.extend(
            [
                MenuItem("section_network_diag", "── 网络诊断 ──", item_type="section", focusable=False),
                MenuItem("test_direct_connection", "测试网络状态（不通过代理）", item_type="action"),
            ]
        )
        return items

    def _build_status_lines(self) -> list[str]:
        """构造子菜单状态栏文本。"""
        if self.status_lines_builder is not None:
            return self.status_lines_builder(self.config, self.session)
        return ["配置已保存" if not self.session.dirty else "有未保存的修改"]

    def _remember_menu_index(self, items: list[MenuItem], key: str) -> None:
        """记住当前菜单光标位置。"""
        for index, item in enumerate(items):
            if item.key == key:
                self.session.menu_index_map["advanced_settings"] = index
                return

    def _mark_network_config_changed(self) -> None:
        """网络配置变更后，同步刷新会话状态。"""
        self.session.network_test_message = ""
        self.session.last_error_text = ""
        self.session.token_status_message = "网络配置已修改，请重新测试"
        self.session.dirty = True
        self.changed = True

    def _handle_test_proxy(self) -> None:
        """测试代理连通性。"""
        proxy = self.config.export_defaults.proxy
        if not proxy.host:
            self.session.network_test_message = "代理未配置，请先设置代理地址"
            return
        try:
            client = self.build_client_from_config(self.config, self.config.token or "")
            success, message = client.test_proxy()
            if success:
                self.session.network_test_message = "代理测试成功"
            else:
                self.session.network_test_message = f"代理测试失败：{message}"
        except Exception as exc:  # noqa: BLE001
            self.session.network_test_message = f"代理测试失败：{exc}"

    def _handle_test_direct_connection(self) -> None:
        """测试直连网络状态。"""
        try:
            client = self.build_client_from_config(self.config, self.config.token or "")
            success, message = client.test_direct_connection()
            if success:
                self.session.network_test_message = "网络正常"
            else:
                self.session.network_test_message = f"网络异常：{message}"
        except Exception as exc:  # noqa: BLE001
            self.session.network_test_message = f"网络异常：{exc}"
