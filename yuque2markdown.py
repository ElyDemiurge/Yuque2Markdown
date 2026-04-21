from __future__ import annotations

import importlib
import locale
import sys

REQUIRED_PYTHON_VERSION = (3, 10)

REQUIRED_MODULES = [
    ("threading", "多线程"),
    ("json", "JSON 处理"),
    ("urllib.request", "网络请求"),
    ("urllib.parse", "URL 解析"),
    ("ssl", "SSL 支持"),
    ("xml.etree.ElementTree", "XML 解析"),
    ("dataclasses", "数据类"),
]


def check_python_version() -> tuple[bool, str]:
    """检查 Python 版本是否满足要求。"""
    if sys.version_info < REQUIRED_PYTHON_VERSION:
        required = f"{REQUIRED_PYTHON_VERSION[0]}.{REQUIRED_PYTHON_VERSION[1]}"
        current = f"{sys.version_info.major}.{sys.version_info.minor}"
        return False, f"需要 Python {required}+，当前版本 {current}"
    return True, ""


def check_modules() -> list[tuple[str, str, str]]:
    """检查必需模块是否可用，返回 (模块名, 用途, 错误信息) 列表。"""
    missing = []
    for module_name, purpose in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
        except ImportError as e:
            missing.append((module_name, purpose, str(e)))
    return missing


def check_runtime_support() -> str:
    """检查当前平台和控制台运行环境是否受支持。"""
    if sys.platform != "darwin":
        return "当前版本仅支持 macOS 运行"
    try:
        importlib.import_module("curses")
    except ImportError as error:
        return f"缺少模块 curses（终端界面）: {error}"
    return ""


def run_startup_checks() -> tuple[bool, list[str]]:
    """运行启动检查，返回 (是否通过, 错误消息列表)。"""
    errors = []

    # 启动阶段优先拦截最基础的问题，避免进入控制台后再以异常形式暴露。
    version_ok, version_error = check_python_version()
    if not version_ok:
        errors.append(version_error)

    missing_modules = check_modules()
    for module_name, purpose, error in missing_modules:
        errors.append(f"缺少模块 {module_name}（{purpose}）: {error}")

    runtime_error = check_runtime_support()
    if runtime_error:
        errors.append(runtime_error)

    return len(errors) == 0, errors


def configure_console_locale() -> None:
    """按当前环境初始化终端 locale，避免宽字符在 curses 下显示异常。"""
    try:
        locale.setlocale(locale.LC_ALL, "")
    except locale.Error:
        return


def main(argv: list[str] | None = None) -> int:
    # 入口保持尽量薄，只负责启动前校验和控制台初始化。
    checks_ok, errors = run_startup_checks()
    if not checks_ok:
        print("启动检查失败：")
        for error in errors:
            print(f"  - {error}")
        print("\n请检查 Python 环境配置后重试。")
        return 1

    argv = argv if argv is not None else sys.argv[1:]
    if argv:
        print("不支持命令行参数，请直接在终端中运行以启动交互式控制台。")
        return 1
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("当前环境不是交互式终端，无法启动 curses 控制台。")
        return 1

    configure_console_locale()

    from curses import error as CursesError
    from core_modules.console import run_console_app

    try:
        return run_console_app()
    except CursesError:
        print("控制台初始化失败，请确认当前运行环境支持交互式终端。")
        return 1


def cli() -> None:
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        print("\n已退出。")
        raise SystemExit(0)


if __name__ == "__main__":
    cli()
