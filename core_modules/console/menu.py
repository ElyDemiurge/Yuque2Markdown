from __future__ import annotations

import importlib
import sys

_BACKEND_NAME = "core_modules.console.menu_windows" if sys.platform.startswith("win") else "core_modules.console.menu_unix"
_backend = importlib.import_module(_BACKEND_NAME)

for _name in dir(_backend):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(_backend, _name)

__all__ = [name for name in globals() if not name.startswith("__")]
