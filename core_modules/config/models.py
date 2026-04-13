from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from core_modules.export.models import ExportOptions

if TYPE_CHECKING:
    from core_modules.console.menu import MenuRefreshState


@dataclass(slots=True)
class ProxyConfig:
    """保存本地代理连接参数。"""
    enabled: bool = False
    host: str = ""
    port: int = 7890
    test_url: str = "https://www.baidu.com"


@dataclass(slots=True)
class ExportDefaultsConfig:
    """保存导出相关默认配置。"""
    output_dir: str = "output"
    resume: bool = True
    strict: bool = False
    request_interval: float = 0.2
    timeout: int = 10
    token_check_timeout: int = 5
    request_max_retries: int = 5
    rate_limit_backoff_seconds: float = 5.0
    network_backoff_seconds: float = 2.0
    max_backoff_seconds: float = 60.0
    max_docs: int | None = None
    offline_assets: bool = True
    assets_dir_name: str = "assets"
    fail_on_asset_error: bool = False
    proxy: ProxyConfig = field(default_factory=ProxyConfig)


@dataclass(slots=True)
class UiPreferences:
    """保存控制台界面的交互偏好。"""
    confirm_before_export: bool = True
    auto_save_after_export: bool = True


@dataclass(slots=True)
class AppConfig:
    """聚合持久化配置文件中的全部设置。"""
    version: int = 1
    token: str = ""
    persist_token: bool = True
    last_repo_input: str = ""
    export_defaults: ExportDefaultsConfig = field(default_factory=ExportDefaultsConfig)
    ui_preferences: UiPreferences = field(default_factory=UiPreferences)


@dataclass(slots=True)
class SessionState:
    """保存控制台运行过程中的临时会话状态。"""
    repo_input: str = ""
    repo_display_name: str = ""
    repo_namespace: str = ""
    repo_url: str = ""
    repo_list_index: int = 0
    repo_filter: str = ""
    selected_doc_ids: set[int] | None = None
    selected_doc_count: int = 0
    last_exported_docs: int = 0
    last_result_summary: list[str] = field(default_factory=list)
    current_user_label: str = "未检查"
    status_message: str = "准备就绪"
    last_warning_message: str = ""
    last_error_text: str = ""
    connection_ok: bool = False
    menu_index_map: dict[str, int] = field(default_factory=dict)
    transient_lines: list[str] = field(default_factory=list)
    menu_refresh_state: MenuRefreshState | None = None
    dirty: bool = False
    # 独立状态字段，避免消息互相覆盖
    token_status_message: str = ""  # Token 连接状态（刷新成功/失败/需刷新/限流）
    config_status_message: str = ""  # 配置更新提示（已更新输出目录等）
    network_test_message: str = ""  # 网络测试结果


def build_export_options(config: AppConfig, repo_input: str, selected_doc_ids: set[int] | None = None) -> ExportOptions:
    """根据当前配置和会话选择构造导出参数。"""
    defaults = config.export_defaults
    return ExportOptions(
        repo_input=repo_input,
        output_dir=Path(defaults.output_dir),
        resume=defaults.resume,
        strict=defaults.strict,
        request_interval=defaults.request_interval,
        max_docs=defaults.max_docs,
        selected_doc_ids=selected_doc_ids,
        offline_assets=defaults.offline_assets,
        assets_dir_name=defaults.assets_dir_name,
        fail_on_asset_error=defaults.fail_on_asset_error,
    )
