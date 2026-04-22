from pathlib import Path

from core_modules.version import APP_VERSION


ROOT = Path(__file__).resolve().parent.parent


def _read_text(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_readme_version_matches_code() -> None:
    readme = _read_text("README.md")
    assert f"当前版本：`{APP_VERSION}`" in readme


def test_readme_uses_esc_instead_of_q_for_return() -> None:
    readme = _read_text("README.md")
    assert "| `q` | 返回或退出 |" not in readme
    assert "| `Esc`（非编辑状态） | 返回上一级或退出当前界面 |" in readme


def test_readme_documents_current_filter_behavior() -> None:
    readme = _read_text("README.md")
    assert "文档树过滤为实时刷新" in readme
    assert "当过滤词命中目录名时，会自动展开该目录并显示目录下文档" in readme
    assert "当过滤词命中折叠目录内的文档时，上层目录路径也会自动显示出来" in readme


def test_architecture_mentions_async_connection_refresh_and_repo_handler_tests() -> None:
    architecture = _read_text("docs/ARCHITECTURE.md")
    assert "控制台中的“刷新连接状态”默认走异步刷新" in architecture
    assert "知识库与文档选择：`test_repo_handler.py`、`test_selector.py`" in architecture


def test_testing_doc_mentions_repo_handler_and_selector_filter_cases() -> None:
    testing_doc = _read_text("docs/TESTING.md")
    assert "`test_repo_handler.py`" in testing_doc
    assert "目录命中后自动展开" in testing_doc
    assert "折叠目录中的命中文档显示" in testing_doc


def test_troubleshooting_documents_filter_debugging_steps() -> None:
    troubleshooting = _read_text("docs/TROUBLESHOOTING.md")
    assert "## 知识库或文档过滤异常" in troubleshooting
    assert "python -m pytest testcases/test_console_menu.py testcases/test_repo_handler.py testcases/test_selector.py" in troubleshooting
    assert "目录会自动展开并显示其子文档" in troubleshooting


def test_config_doc_mentions_current_version_and_attachment_suffix_controls() -> None:
    config_doc = _read_text("docs/配置文件说明.md")
    assert f"当前文档基于 `{APP_VERSION}` 的控制台实现整理。" in config_doc
    assert "控制台中支持按分组切换、逐项切换，以及手动输入其他扩展名。" in config_doc


def test_api_doc_distinguishes_current_project_usage_from_reference_capabilities() -> None:
    api_doc = _read_text("docs/语雀官方接口说明.md")
    assert "### 当前代码实际接入的接口" in api_doc
    assert "#### Cookie / 网页端模式" in api_doc
    assert "## 18. 与当前项目实现的差异" in api_doc


def test_lake_doc_mentions_current_supported_cards_and_fallbacks() -> None:
    lake_doc = _read_text("docs/语雀lake格式解析.md")
    assert f"当前文档基于 `{APP_VERSION}` 的实现整理" in lake_doc
    assert "#### mention" in lake_doc
    assert "#### table" in lake_doc
    assert "正文仅含空段落或占位节点，请核对语雀原文以防文档丢失" in lake_doc
