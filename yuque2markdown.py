from __future__ import annotations

import sys

REQUIRED_PYTHON_VERSION = (3, 10)

REQUIRED_MODULES = [
    ("curses", "终端界面"),
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
            __import__(module_name)
        except ImportError as e:
            missing.append((module_name, purpose, str(e)))
    return missing


def run_startup_checks() -> tuple[bool, list[str]]:
    """运行启动检查，返回 (是否通过, 错误消息列表)。"""
    errors = []

    # 检查 Python 版本
    version_ok, version_error = check_python_version()
    if not version_ok:
        errors.append(version_error)

    # 检查模块
    missing_modules = check_modules()
    for module_name, purpose, error in missing_modules:
        errors.append(f"缺少模块 {module_name}（{purpose}）: {error}")

    return len(errors) == 0, errors


def main(argv: list[str] | None = None) -> int:
    # 启动检查
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
