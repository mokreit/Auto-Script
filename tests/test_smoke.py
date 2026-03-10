from __future__ import annotations

import json
import os
import shutil
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QPoint, QTimer
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QListView, QPushButton

from app.core.models import CompletionMode, RunSettings, ScriptDefinition, TaskStatus
from app.core.runner import ScriptRunner
from app.services.config_service import (
    AppConfig,
    ConfigService,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
)
from app.ui.main_window import MainWindow
from app.ui.script_editor_dialog import ScriptEditorDialog
from app.ui.theme import COMBO_ARROW_PATH, STYLESHEET
from app.ui.widgets.animated_combo_box import AnimatedComboBox, NoWheelListView
from app.ui.widgets.switch import Switch

APP = QApplication.instance() or QApplication([])
WORKSPACE_TEMP_ROOT = Path(__file__).resolve().parents[1] / ".tmp" / "tests"
WORKSPACE_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


@contextmanager
def workspace_temp_dir(prefix: str):
    directory = WORKSPACE_TEMP_ROOT / f"{prefix}-{uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=True)
    try:
        yield directory
    finally:
        shutil.rmtree(directory, ignore_errors=True)


class FakeConfigService:
    def __init__(self, config: AppConfig) -> None:
        self.config_path = Path("D:/test/config.json")
        self._config = config
        self.saved_configs: list[AppConfig] = []

    def load(self) -> tuple[AppConfig, bool]:
        return self._config, True

    def save(self, config: AppConfig) -> None:
        self.saved_configs.append(config)


class ConfigServiceTests(unittest.TestCase):
    def test_round_trip_preserves_scripts_and_settings(self) -> None:
        with workspace_temp_dir("config") as temp_dir:
            config_path = temp_dir / "config.json"
            service = ConfigService(config_path)
            config = AppConfig(
                scripts=[
                    ScriptDefinition.create(
                        name="Smoke",
                        executable_path=sys.executable,
                        arguments="--version",
                        script_process_name="tool.exe",
                        monitor_process_name="game.exe",
                        completion_mode=CompletionMode.SCRIPT_PROCESS,
                        run_timeout_seconds=123,
                        close_script_on_finish=True,
                        close_game_on_finish=True,
                    )
                ],
                run_settings=RunSettings(
                    continue_on_failure=False,
                    auto_clear_log_on_start=False,
                    show_completion_dialog=True,
                    terminate_timeout_seconds=5,
                ),
                window_width=MIN_WINDOW_WIDTH - 200,
                window_height=MIN_WINDOW_HEIGHT - 200,
            )

            service.save(config)
            loaded_config, loaded_from_disk = service.load()

            self.assertTrue(loaded_from_disk)
            self.assertEqual(len(loaded_config.scripts), 1)
            self.assertEqual(loaded_config.scripts[0].name, "Smoke")
            self.assertEqual(loaded_config.scripts[0].script_process_name, "tool.exe")
            self.assertEqual(loaded_config.scripts[0].monitor_process_name, "game.exe")
            self.assertEqual(
                loaded_config.scripts[0].completion_mode,
                CompletionMode.SCRIPT_PROCESS,
            )
            self.assertEqual(loaded_config.scripts[0].run_timeout_seconds, 123)
            self.assertFalse(loaded_config.run_settings.continue_on_failure)
            self.assertFalse(loaded_config.run_settings.auto_clear_log_on_start)
            self.assertTrue(loaded_config.run_settings.show_completion_dialog)
            self.assertEqual(loaded_config.run_settings.terminate_timeout_seconds, 5)
            self.assertEqual(loaded_config.window_width, MIN_WINDOW_WIDTH)
            self.assertEqual(loaded_config.window_height, MIN_WINDOW_HEIGHT)

    def test_load_legacy_config_defaults_to_game_completion_when_game_process_exists(self) -> None:
        with workspace_temp_dir("legacy-config") as temp_dir:
            config_path = temp_dir / "config.json"
            config_path.write_text(
                """
{
  "scripts": [
    {
      "script_id": "legacy",
      "name": "Legacy",
      "executable_path": "tool.exe",
      "monitor_process_name": "game.exe",
      "enabled": true
    }
  ],
  "settings": {},
  "window": {}
}
                """.strip(),
                encoding="utf-8",
            )

            service = ConfigService(config_path)
            loaded_config, loaded_from_disk = service.load()

            self.assertTrue(loaded_from_disk)
            self.assertEqual(len(loaded_config.scripts), 1)
            self.assertEqual(
                loaded_config.scripts[0].completion_mode,
                CompletionMode.GAME_PROCESS,
            )


class MainWindowSmokeTests(unittest.TestCase):
    def test_main_window_builds_from_config_service(self) -> None:
        config = AppConfig(
            scripts=[
                ScriptDefinition.create(
                    name="主窗口冒烟",
                    executable_path=sys.executable,
                )
            ]
        )
        fake_service = FakeConfigService(config)

        with patch("app.ui.main_window.ConfigService", return_value=fake_service):
            window = MainWindow()

        try:
            self.assertEqual(window.windowTitle(), "Auto-Script")
            self.assertEqual(window.script_summary_label.text(), "1 脚本 / 1 启用")
            self.assertEqual(window.donate_page_button.text(), "赞赏")
            self.assertEqual(window.page_stack.count(), 4)
            self.assertEqual(window.current_task_label.text(), "运行状态: 待机")
            self.assertEqual(window.next_task_label.text(), "待执行: 主窗口冒烟")
        finally:
            window.close()

    def test_main_window_toggle_updates_script_state_and_summary(self) -> None:
        config = AppConfig(
            scripts=[
                ScriptDefinition.create(
                    name="Toggle Smoke",
                    executable_path=sys.executable,
                )
            ]
        )
        fake_service = FakeConfigService(config)

        with patch("app.ui.main_window.ConfigService", return_value=fake_service):
            window = MainWindow()

        try:
            toggle = window.findChild(Switch)
            self.assertIsNotNone(toggle)
            self.assertTrue(window.scripts[0].enabled)
            self.assertEqual(window.script_summary_label.text(), "1 脚本 / 1 启用")

            assert toggle is not None
            toggle.click()

            self.assertFalse(window.scripts[0].enabled)
            self.assertEqual(window.script_summary_label.text(), "1 脚本 / 0 启用")
            self.assertTrue(fake_service.saved_configs)
        finally:
            window.close()

    def test_main_window_script_cards_use_compact_spacing(self) -> None:
        config = AppConfig(
            scripts=[
                ScriptDefinition.create(
                    name="Compact Card",
                    executable_path=sys.executable,
                )
            ]
        )
        fake_service = FakeConfigService(config)

        with patch("app.ui.main_window.ConfigService", return_value=fake_service):
            window = MainWindow()

        try:
            script_card = window.findChild(QFrame, "ScriptCard")
            self.assertIsNotNone(script_card)
            assert script_card is not None

            layout = script_card.layout()
            self.assertIsNotNone(layout)
            assert layout is not None
            margins = layout.contentsMargins()
            self.assertEqual(
                (margins.left(), margins.top(), margins.right(), margins.bottom()),
                (16, 16, 16, 16),
            )
            self.assertEqual(layout.spacing(), 8)
            self.assertEqual(window.script_cards_layout.spacing(), 8)

            action_buttons = [
                button
                for button in script_card.findChildren(QPushButton)
                if button.text() in {"上移", "下移", "编辑", "删除"}
            ]
            self.assertEqual(len(action_buttons), 4)
            self.assertTrue(
                all(button.property("compact") is True for button in action_buttons)
            )
            self.assertIn('QPushButton[compact="true"]', STYLESHEET)
        finally:
            window.close()

    def test_main_window_log_panel_uses_larger_default_area(self) -> None:
        config = AppConfig(
            scripts=[
                ScriptDefinition.create(
                    name="Log Layout",
                    executable_path=sys.executable,
                )
            ]
        )
        fake_service = FakeConfigService(config)

        with patch("app.ui.main_window.ConfigService", return_value=fake_service):
            window = MainWindow()

        try:
            window.resize(1200, 800)
            self.assertEqual(window._default_splitter_sizes(), [360, 900])
            self.assertEqual(window.start_button.property("compact"), True)
            self.assertEqual(window.stop_button.property("compact"), True)
            self.assertEqual(window.skip_button.property("compact"), True)
            self.assertEqual(window.clear_log_button.property("compact"), True)
            self.assertIn("QLabel#LogPanelTitle", STYLESHEET)
        finally:
            window.close()

    def test_main_window_timeout_tag_uses_timeout_wording(self) -> None:
        config = AppConfig(
            scripts=[
                ScriptDefinition.create(
                    name="Timeout Label",
                    executable_path=sys.executable,
                    run_timeout_seconds=600,
                )
            ]
        )
        fake_service = FakeConfigService(config)

        with patch("app.ui.main_window.ConfigService", return_value=fake_service):
            window = MainWindow()

        try:
            tags = window._script_tags(window.scripts[0])
            self.assertEqual(tags[0][0], "超时 600 秒（10 分钟）")
        finally:
            window.close()

    def test_main_window_switch_config_file_saves_current_state(self) -> None:
        config = AppConfig(
            scripts=[
                ScriptDefinition.create(
                    name="Current Config",
                    executable_path=sys.executable,
                )
            ]
        )
        fake_service = FakeConfigService(config)

        with patch("app.ui.main_window.ConfigService", return_value=fake_service):
            window = MainWindow()

        try:
            with workspace_temp_dir("config-switch-save") as temp_dir:
                selected_path = temp_dir / "selected-config.json"

                self.assertTrue(window._switch_config_file(selected_path))
                self.assertEqual(window.config_path_detail.text(), str(selected_path))
                self.assertEqual(window.config_service.config_path, selected_path)

                payload = json.loads(selected_path.read_text(encoding="utf-8"))
                self.assertEqual(payload["scripts"][0]["name"], "Current Config")
        finally:
            window.close()

    def test_main_window_switch_config_file_loads_existing_config(self) -> None:
        config = AppConfig(
            scripts=[
                ScriptDefinition.create(
                    name="Original Config",
                    executable_path=sys.executable,
                )
            ]
        )
        fake_service = FakeConfigService(config)

        with patch("app.ui.main_window.ConfigService", return_value=fake_service):
            window = MainWindow()

        try:
            with workspace_temp_dir("config-switch-load") as temp_dir:
                selected_path = temp_dir / "selected-config.json"
                ConfigService(selected_path).save(
                    AppConfig(
                        scripts=[
                            ScriptDefinition.create(
                                name="Loaded Config",
                                executable_path=sys.executable,
                            )
                        ],
                        run_settings=RunSettings(
                            continue_on_failure=False,
                            auto_clear_log_on_start=False,
                            show_completion_dialog=True,
                            terminate_timeout_seconds=7,
                        ),
                    )
                )

                self.assertTrue(window._switch_config_file(selected_path))
                self.assertEqual(window.config_path_detail.text(), str(selected_path))
                self.assertEqual(window.config_service.config_path, selected_path)
                self.assertEqual(window.scripts[0].name, "Loaded Config")
                self.assertFalse(window.continue_on_failure_checkbox.isChecked())
                self.assertFalse(window.auto_clear_log_checkbox.isChecked())
                self.assertTrue(window.show_completion_dialog_checkbox.isChecked())
                self.assertEqual(window.terminate_timeout_spin.value(), 7)
        finally:
            window.close()


class ScriptEditorDialogSmokeTests(unittest.TestCase):
    def test_monitor_process_combo_uses_styled_popup_view(self) -> None:
        dialog = ScriptEditorDialog()

        try:
            self.assertGreaterEqual(dialog.height(), ScriptEditorDialog.DIALOG_HEIGHT)
            self.assertIsInstance(dialog.monitor_process_name_edit, AnimatedComboBox)
            self.assertEqual(
                dialog.monitor_process_name_edit.property("wideDropDownHitbox"),
                True,
            )
            self.assertIsInstance(dialog.monitor_process_name_edit.view(), QListView)
            self.assertIsInstance(dialog.monitor_process_name_edit.view(), NoWheelListView)
            self.assertEqual(
                dialog.monitor_process_name_edit.view().objectName(),
                "ComboPopupView",
            )
            popup_container = dialog.monitor_process_name_edit.view().parentWidget()
            self.assertIsNotNone(popup_container)
            assert popup_container is not None
            self.assertEqual(popup_container.objectName(), "ComboPopupContainer")
            self.assertEqual(popup_container.frameShape(), popup_container.Shape.NoFrame)
            self.assertTrue(
                popup_container.testAttribute(
                    Qt.WidgetAttribute.WA_TranslucentBackground
                )
            )
            self.assertIn("QAbstractItemView#ComboPopupView", STYLESHEET)
            self.assertIn("QFrame#ComboPopupContainer", STYLESHEET)
            self.assertIn("background: transparent;", STYLESHEET)
            self.assertIn('QComboBox[wideDropDownHitbox="true"]', STYLESHEET)
            self.assertIn(
                "QAbstractItemView#ComboPopupView::item:selected",
                STYLESHEET,
            )
        finally:
            dialog.close()

    def test_theme_defines_combo_arrow_asset(self) -> None:
        self.assertTrue(Path(COMBO_ARROW_PATH).exists())
        self.assertIn("QComboBox::down-arrow", STYLESHEET)
        self.assertIn("combobox-popup: 0;", STYLESHEET)
        self.assertIn(COMBO_ARROW_PATH, STYLESHEET)

    def test_monitor_process_presets_are_available(self) -> None:
        dialog = ScriptEditorDialog()

        try:
            self.assertEqual(
                [
                    dialog.monitor_process_name_edit.itemText(index)
                    for index in range(dialog.monitor_process_name_edit.count())
                ],
                [
                    "原神",
                    "崩坏：星穹铁道",
                    "绝区零",
                    "无限暖暖",
                ],
            )
            self.assertEqual(dialog.monitor_process_name_edit.currentText(), "")
        finally:
            dialog.close()

    def test_script_editor_defaults_finish_switches_to_enabled(self) -> None:
        dialog = ScriptEditorDialog()

        try:
            self.assertTrue(dialog.close_script_on_finish_switch.isChecked())
            self.assertTrue(dialog.close_game_on_finish_switch.isChecked())
            self.assertEqual(dialog.monitor_process_name_edit.currentText(), "")
        finally:
            dialog.close()

    def test_build_script_always_uses_game_completion_mode(self) -> None:
        script = ScriptDefinition.create(
            name="Legacy Launch Mode",
            executable_path=sys.executable,
            monitor_process_name="game.exe",
            completion_mode=CompletionMode.LAUNCH_PROCESS,
        )
        dialog = ScriptEditorDialog(script=script)

        try:
            built_script = dialog.build_script()
            self.assertEqual(
                built_script.completion_mode,
                CompletionMode.GAME_PROCESS,
            )
        finally:
            dialog.close()

    def test_monitor_process_is_required_when_validating_script(self) -> None:
        dialog = ScriptEditorDialog()
        dialog.name_edit.setText("Game Task")
        dialog.path_edit.setText(sys.executable)
        dialog.monitor_process_name_edit.setCurrentText("")

        with patch("app.ui.script_editor_dialog.QMessageBox.warning") as warning:
            dialog._validate_and_accept()

        warning.assert_called_once()
        dialog.close()

    def test_monitor_process_preset_selection_fills_process_name(self) -> None:
        dialog = ScriptEditorDialog()

        try:
            dialog._apply_monitor_process_preset_by_index(0)
            self.assertEqual(
                dialog.monitor_process_name_edit.currentText(),
                "YuanShen.exe",
            )
        finally:
            dialog.close()

    def test_monitor_process_combo_targets_popup_below_field(self) -> None:
        dialog = ScriptEditorDialog()

        try:
            dialog.show()
            APP.processEvents()

            combo = dialog.monitor_process_name_edit
            combo.showPopup()
            APP.processEvents()
            target_rect = combo._popup_target_rect()
            popup_view_rect = combo._popup_view_rect(target_rect)
            start_rect = combo._popup_start_rect(target_rect)
            combo_bottom = combo.mapToGlobal(QPoint(0, combo.height())).y()

            self.assertGreaterEqual(
                target_rect.y(),
                combo_bottom + combo.POPUP_OFFSET_Y,
            )
            self.assertFalse(combo.view().hasAutoScroll())
            self.assertEqual(combo.view().spacing(), combo.POPUP_ITEM_SPACING_Y)
            self.assertEqual(
                combo.view().verticalScrollBarPolicy(),
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
            )
            self.assertEqual(popup_view_rect.y(), 0)
            self.assertLess(start_rect.y(), popup_view_rect.y())
            self.assertGreater(
                combo._popup_content_height(),
                combo.POPUP_ITEM_MIN_HEIGHT * combo.count(),
            )
            self.assertEqual(combo.POPUP_ANIMATION_DURATION_MS, 160)
        finally:
            dialog.monitor_process_name_edit.hidePopup()
            dialog.close()

    def test_monitor_process_combo_uses_wider_drop_down_hitbox(self) -> None:
        dialog = ScriptEditorDialog()

        try:
            combo = dialog.monitor_process_name_edit
            combo.resize(240, 40)
            self.assertEqual(combo._drop_down_hitbox_width(), 40)
            self.assertTrue(combo._is_drop_down_hit(QPoint(combo.width() - 12, 20)))
            self.assertFalse(combo._is_drop_down_hit(QPoint(24, 20)))
        finally:
            dialog.close()


class ScriptRunnerSmokeTests(unittest.TestCase):
    def test_runner_executes_script_successfully(self) -> None:
        with workspace_temp_dir("runner") as temp_dir:
            script_path = temp_dir / "runner_smoke.py"
            script_path.write_text(
                "print('runner-smoke-ok', flush=True)\n",
                encoding="utf-8",
            )
            script = ScriptDefinition.create(
                name="Runner Smoke",
                executable_path=sys.executable,
                arguments=f'"{script_path}"',
            )
            runner = ScriptRunner()
            outputs: list[str] = []
            finished_contexts = []
            execution_results: list[tuple[bool, str]] = []
            timed_out = {"value": False}
            loop = QEventLoop()

            def handle_output(_context, _stream: str, text: str) -> None:
                outputs.append(text)

            def handle_finished(context) -> None:
                finished_contexts.append(context)

            def handle_execution_finished(completed: bool, message: str) -> None:
                execution_results.append((completed, message))
                loop.quit()

            def handle_timeout() -> None:
                timed_out["value"] = True
                loop.quit()

            runner.script_output.connect(handle_output)
            runner.script_finished.connect(handle_finished)
            runner.execution_finished.connect(handle_execution_finished)

            self.assertTrue(runner.start([script]))
            QTimer.singleShot(10000, handle_timeout)
            loop.exec()

            self.assertFalse(timed_out["value"])
            self.assertEqual(len(execution_results), 1)
            self.assertTrue(execution_results[0][0])
            self.assertEqual(len(finished_contexts), 1)
            self.assertEqual(finished_contexts[0].status, TaskStatus.SUCCESS)
            self.assertTrue(any("runner-smoke-ok" in output for output in outputs))


class ScriptRunnerProcessTests(unittest.TestCase):
    def test_resolve_completion_process_name_uses_script_process_when_selected(self) -> None:
        runner = ScriptRunner()
        runner._script_process_name = "BetterGI.exe"
        runner._game_process_name = "YuanShen.exe"
        runner._completion_mode = CompletionMode.SCRIPT_PROCESS

        self.assertEqual(runner._resolve_completion_process_name(), "BetterGI.exe")

    def test_request_current_process_stop_prefers_script_process_name(self) -> None:
        runner = ScriptRunner()
        runner._process = Mock()
        runner._process.poll.return_value = None
        runner._process.pid = 123
        runner._close_script_on_finish = True
        runner._script_process_name = "BetterGI.exe"

        with patch.object(
            runner,
            "_terminate_processes_by_image_name",
            return_value=True,
        ) as terminate_by_name:
            with patch.object(runner, "_terminate_process_tree") as terminate_tree:
                runner._request_current_process_stop()

        terminate_by_name.assert_called_once_with("BetterGI.exe")
        terminate_tree.assert_not_called()

    def test_update_runtime_settings_applies_immediately(self) -> None:
        runner = ScriptRunner()
        runner._process = Mock()
        runner._process.poll.return_value = None
        runner._continue_on_failure = True
        runner._terminate_timeout_seconds = 3.0
        runner._stop_deadline = 1.0

        runner.update_runtime_settings(
            continue_on_failure=False,
            terminate_timeout_seconds=7.0,
        )

        self.assertFalse(runner._continue_on_failure)
        self.assertEqual(runner._terminate_timeout_seconds, 7.0)
        self.assertGreater(runner._stop_deadline, 1.0)


if __name__ == "__main__":
    unittest.main()
