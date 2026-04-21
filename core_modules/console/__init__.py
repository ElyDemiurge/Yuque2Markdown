def run_console_app() -> int:
    from core_modules.console.app import run_console_app as _run_console_app

    return _run_console_app()


__all__ = ["run_console_app"]
