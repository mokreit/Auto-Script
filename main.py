from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.ui.theme import apply_theme

AUTO_ELEVATE_ENV = "SCRIPT_SCHEDULER_SKIP_ELEVATION"


def _preferred_windows_python_executable() -> str:
    current_executable = Path(sys.executable)
    if not sys.platform.startswith("win"):
        return str(current_executable)

    if current_executable.name.lower() != "python.exe":
        return str(current_executable)

    gui_executable = current_executable.with_name("pythonw.exe")
    if gui_executable.exists():
        return str(gui_executable)
    return str(current_executable)


def relaunch_as_admin_if_needed(argv: list[str] | None = None) -> int | None:
    if not sys.platform.startswith("win"):
        return None
    if os.environ.get(AUTO_ELEVATE_ENV) == "1":
        return None
    if _is_user_admin():
        return None

    argv = argv or sys.argv
    parameters = subprocess.list2cmdline(argv)
    result = ctypes.windll.shell32.ShellExecuteW(  # type: ignore[attr-defined]
        None,
        "runas",
        _preferred_windows_python_executable(),
        parameters,
        None,
        1,
    )
    return 0 if result > 32 else 1


def _is_user_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        return False


def main() -> int:
    relaunch_code = relaunch_as_admin_if_needed()
    if relaunch_code is not None:
        return relaunch_code

    app = QApplication(sys.argv)
    app.setApplicationName("Auto-Script")
    app.setOrganizationName("ScriptScheduler")
    apply_theme(app)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
