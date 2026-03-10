from __future__ import annotations

import os
import unittest
from unittest.mock import patch

import main


class MainElevationTests(unittest.TestCase):
    def test_preferred_windows_python_executable_uses_pythonw_when_available(self) -> None:
        with patch("main.sys.platform", "win32"):
            with patch("main.sys.executable", r"C:\Python312\python.exe"):
                with patch("main.Path.exists", return_value=True):
                    self.assertTrue(
                        main._preferred_windows_python_executable().endswith(
                            "pythonw.exe"
                        )
                    )

    def test_skip_elevation_env_bypasses_relaunch(self) -> None:
        with patch.dict(os.environ, {main.AUTO_ELEVATE_ENV: "1"}, clear=False):
            self.assertIsNone(main.relaunch_as_admin_if_needed(["main.py"]))

    def test_already_admin_does_not_relaunch(self) -> None:
        with patch.dict(os.environ, {main.AUTO_ELEVATE_ENV: "0"}, clear=False):
            with patch("main._is_user_admin", return_value=True):
                self.assertIsNone(main.relaunch_as_admin_if_needed(["main.py"]))

    def test_relaunch_returns_success_code_when_shell_execute_succeeds(self) -> None:
        with patch.dict(os.environ, {main.AUTO_ELEVATE_ENV: "0"}, clear=False):
            with patch("main._is_user_admin", return_value=False):
                with patch("main.ctypes.windll.shell32.ShellExecuteW", return_value=33):
                    self.assertEqual(main.relaunch_as_admin_if_needed(["main.py"]), 0)


if __name__ == "__main__":
    unittest.main()
