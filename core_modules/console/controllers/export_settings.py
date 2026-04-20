"""导出设置子菜单控制器。"""

from core_modules.config.models import AUTH_MODE_COOKIE, AppConfig, SessionState, normalize_auth_mode, normalize_attachment_suffixes, parse_attachment_suffixes_input
from core_modules.console.helpers import parse_action, toggle_config_value
from core_modules.console.menu import InlineChoice, MenuItem, run_menu, show_message
from core_modules.config.validator import ATTACHMENT_SUFFIX_PATTERN

ATTACHMENT_SUFFIX_GROUPS = {
    "archives": ("压缩包", [".zip", ".rar", ".7z"]),
    "docs": ("文档", [".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"]),
    "media": ("媒体文件", [".mp3", ".mp4"]),
}
ATTACHMENT_SUFFIX_ROW_GROUPS = {
    "archives": [[".zip", ".rar", ".7z"]],
    "docs": [[".pdf", ".doc", ".docx", ".xls", ".xlsx"], [".ppt", ".pptx"]],
    "media": [[".mp3", ".mp4"]],
}
ATTACHMENT_DOWNLOAD_DISABLED_TEXT = "使用 Token 登录时无法下载附件以及选择下载附件类型；如需下载附件，请切换到浏览器 Cookie 登录。"
ATTACHMENT_ALL_TITLE = "下载全部附件"


class ExportSettingsController:
    """管理“导出路径与资源”子菜单。"""

    def __init__(self, config: AppConfig, session: SessionState, *, status_lines_builder=None):
        self.config = config
        self.session = session
        self.status_lines_builder = status_lines_builder
        self.changed = False
        self.attachment_row_selected_index: dict[str, int] = {}

    def run(self) -> bool:
        """运行“导出路径与资源”子菜单并处理交互。"""
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
            elif key == "attachment_suffixes_all":
                self._toggle_attachment_all()
            elif key.startswith("attachment_group__"):
                self._toggle_attachment_group(key.removeprefix("attachment_group__"))
            elif key == "attachment_custom_suffixes" and edited_value is not None:
                self._handle_custom_attachment_suffixes(edited_value)
            elif key.startswith("attachment_suffix__"):
                self._toggle_attachment_suffix("." + key.removeprefix("attachment_suffix__"))

    def _build_menu_items(self) -> list[MenuItem]:
        """构造导出设置菜单项。"""
        attachment_enabled = normalize_auth_mode(self.config.auth_mode) == AUTH_MODE_COOKIE
        items = [
            MenuItem("section_paths", "── 路径与资源 ──", item_type="section", focusable=False),
            MenuItem("output_dir", "输出目录", self.config.export_defaults.output_dir, input_style=True),
            MenuItem("assets_dir_name", "资源目录名", self.config.export_defaults.assets_dir_name, input_style=True),
            MenuItem("section_flags", "── 导出行为 ──", item_type="section", focusable=False),
            MenuItem("resume", "断点恢复", self._bool_text(self.config.export_defaults.resume), item_type="bool"),
            MenuItem("strict", "严格模式", self._bool_text(self.config.export_defaults.strict), item_type="bool"),
            MenuItem("offline_assets", "离线资源", self._bool_text(self.config.export_defaults.offline_assets), item_type="bool"),
            MenuItem("section_attachments", "── 附件资源下载 ──", item_type="section", focusable=False),
        ]
        if not attachment_enabled:
            items.append(
                MenuItem(
                    "attachment_disabled",
                    "[-] 附件下载",
                    ATTACHMENT_DOWNLOAD_DISABLED_TEXT,
                    item_type="readonly",
                    focusable=False,
                )
            )
            items.append(
                MenuItem(
                    "fail_on_asset_error",
                    "资源下载失败时中止导出",
                    self._bool_text(self.config.export_defaults.fail_on_asset_error),
                    item_type="bool",
                )
            )
            return items

        items.append(
            MenuItem(
                "attachment_suffixes_all",
                ATTACHMENT_ALL_TITLE,
                self._bool_text(self._all_resources_enabled()),
                item_type="check",
                indent=0,
                focusable=True,
            ),
        )
        items.extend(self._build_attachment_suffix_items(disabled=False))
        items.append(
            MenuItem(
                "fail_on_asset_error",
                "资源下载失败时中止导出",
                self._bool_text(self.config.export_defaults.fail_on_asset_error),
                item_type="bool",
            )
        )
        return items

    def _build_attachment_suffix_items(self, *, disabled: bool) -> list[MenuItem]:
        selected = normalize_attachment_suffixes(self.config.export_defaults.attachment_suffixes)
        items: list[MenuItem] = []
        for group_key in ("archives", "docs", "media"):
            label, suffixes = ATTACHMENT_SUFFIX_GROUPS[group_key]
            group_selected = selected == ["*"] or self._group_selected(selected, suffixes)
            items.append(
                MenuItem(
                    f"attachment_group__{group_key}",
                    label,
                    self._bool_text(group_selected) if not disabled else ATTACHMENT_DOWNLOAD_DISABLED_TEXT,
                    item_type="readonly" if disabled else "check",
                    indent=1,
                    focusable=not disabled,
                )
            )
            for row_index, row_suffixes in enumerate(ATTACHMENT_SUFFIX_ROW_GROUPS[group_key]):
                row_key = f"attachment_row__{group_key}__{row_index}"
                items.append(
                    MenuItem(
                        row_key,
                        "",
                        item_type="readonly" if disabled else "action",
                        indent=2,
                        focusable=not disabled,
                        inline_choices=[
                            InlineChoice(
                                key=f"attachment_suffix__{suffix.lstrip('.')}",
                                label=suffix,
                                checked=selected == ["*"] or suffix in selected,
                            )
                            for suffix in row_suffixes
                        ],
                        inline_selected_index=self.attachment_row_selected_index.get(row_key, 0),
                    )
                )
        items.append(
            MenuItem(
                "attachment_custom_suffixes",
                "其他类型的文件（填写扩展名，使用\",\"分割）",
                ", ".join(self._custom_suffixes(selected)) or "未设置",
                item_type="readonly" if disabled else "check",
                input_style=True,
                edit_value=", ".join(self._custom_suffixes(selected)),
                indent=1,
                focusable=not disabled,
            )
        )
        return items

    def _build_status_lines(self) -> list[str]:
        """构造子菜单状态栏文本。"""
        if self.status_lines_builder is not None:
            return self.status_lines_builder(self.config, self.session)
        return ["配置已保存" if not self.session.dirty else "有未保存的修改"]

    def _handle_output_dir(self, value: str) -> None:
        """处理输出目录修改。"""
        if value:
            self.config.export_defaults.output_dir = value
            self.session.status_message = "已更新输出目录"
            self.session.dirty = True
            self.changed = True

    def _handle_assets_dir(self, value: str) -> None:
        """处理资源目录名修改。"""
        if value:
            self.config.export_defaults.assets_dir_name = value
            self.session.status_message = "已更新资源目录名"
            self.session.dirty = True
            self.changed = True

    def _handle_toggle(self, key: str) -> None:
        """处理布尔开关项切换。"""
        toggle_config_value(self.config, key)
        label_map = {
            "resume": "断点恢复",
            "strict": "严格模式",
            "offline_assets": "离线资源",
            "fail_on_asset_error": "资源下载失败时中止导出",
        }
        self.session.status_message = f"已更新{label_map.get(key, key)}"
        self.session.dirty = True
        self.changed = True

    def _all_resources_enabled(self) -> bool:
        return normalize_attachment_suffixes(self.config.export_defaults.attachment_suffixes) == ["*"]

    def _toggle_attachment_all(self) -> None:
        self._apply_attachment_suffixes([] if self._all_resources_enabled() else ["*"])

    def _toggle_attachment_group(self, group_key: str) -> None:
        selected = normalize_attachment_suffixes(self.config.export_defaults.attachment_suffixes)
        if selected == ["*"]:
            selected = []
        _, suffixes = ATTACHMENT_SUFFIX_GROUPS[group_key]
        if self._group_selected(selected, suffixes):
            selected = [suffix for suffix in selected if suffix not in suffixes]
        else:
            for suffix in suffixes:
                if suffix not in selected:
                    selected.append(suffix)
        self._apply_attachment_suffixes(selected)

    def _toggle_attachment_suffix(self, suffix: str) -> None:
        selected = normalize_attachment_suffixes(self.config.export_defaults.attachment_suffixes)
        if selected == ["*"]:
            selected = []
        if suffix in selected:
            selected.remove(suffix)
        else:
            selected.append(suffix)
        self._apply_attachment_suffixes(selected)

    def _group_selected(self, selected: list[str], suffixes: list[str]) -> bool:
        return bool(suffixes) and all(suffix in selected for suffix in suffixes)

    def _custom_suffixes(self, selected: list[str]) -> list[str]:
        known = {suffix for _label, suffixes in ATTACHMENT_SUFFIX_GROUPS.values() for suffix in suffixes}
        return [suffix for suffix in selected if suffix not in known and suffix != "*"]

    def _apply_attachment_suffixes(self, values: list[str]) -> None:
        self.config.export_defaults.attachment_suffixes = normalize_attachment_suffixes(values)
        self._mark_attachment_suffixes_changed()

    def _handle_custom_attachment_suffixes(self, value: str) -> None:
        raw = value.replace("，", ",").strip()
        selected = normalize_attachment_suffixes(self.config.export_defaults.attachment_suffixes)
        if selected == ["*"]:
            selected = []
        base_suffixes = [suffix for suffix in selected if suffix not in self._custom_suffixes(selected)]
        if raw and not any(part.strip() for part in raw.split(",")):
            show_message("扩展名无效", ["请输入至少一个扩展名，例如 .epub,.mobi"])
            return
        custom_suffixes = parse_attachment_suffixes_input(raw)
        invalid_values = [suffix for suffix in custom_suffixes if suffix == "*" or not ATTACHMENT_SUFFIX_PATTERN.match(suffix)]
        if invalid_values:
            show_message("扩展名无效", [f"以下扩展名格式无效: {', '.join(invalid_values)}", "请使用 .pdf,.epub 这类格式。"])
            return
        self._apply_attachment_suffixes(base_suffixes + custom_suffixes)

    def _remember_menu_index(self, items: list[MenuItem], key: str) -> None:
        """记录当前菜单索引和行内光标位置。"""
        for index, item in enumerate(items):
            if item.key == key:
                self.session.menu_index_map["export_settings"] = index
                return
            if item.inline_choices:
                for choice_index, choice in enumerate(item.inline_choices):
                    if choice.key == key:
                        self.session.menu_index_map["export_settings"] = index
                        self.attachment_row_selected_index[item.key] = choice_index
                        return

    def _mark_attachment_suffixes_changed(self) -> None:
        selected = normalize_attachment_suffixes(self.config.export_defaults.attachment_suffixes)
        if selected == ["*"]:
            message = "已更新附件资源下载: 所有资源"
        elif not selected:
            message = "已更新附件资源下载: 不下载附件"
        else:
            message = f"已更新附件资源下载: {', '.join(selected)}"
        self.session.status_message = message
        self.session.dirty = True
        self.changed = True

    def _bool_text(self, value: bool) -> str:
        """将布尔值转为界面文案。"""
        return "开启" if value else "关闭"
