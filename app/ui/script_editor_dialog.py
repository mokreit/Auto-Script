from __future__ import annotations

import os
import shutil
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QComboBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    DEFAULT_RUN_TIMEOUT_SECONDS,
    CompletionMode,
    ScriptDefinition,
)
from app.ui.design import SPACE_1, SPACE_2, SPACE_3, apply_elevation
from app.ui.widgets.animated_combo_box import AnimatedComboBox
from app.ui.widgets.switch import Switch


class ScriptEditorDialog(QDialog):
    DIALOG_WIDTH = 720
    DIALOG_HEIGHT = 648
    MONITOR_PROCESS_PRESETS = (
        ("原神", "YuanShen.exe"),
        ("崩坏：星穹铁道", "StarRail.exe"),
        ("绝区零", "ZenlessZoneZero.exe"),
        ("无限暖暖", "X6Game-Win64-Shipping.exe"),
    )

    def __init__(
        self,
        parent: QWidget | None = None,
        script: ScriptDefinition | None = None,
    ) -> None:
        super().__init__(parent)
        self._script = script

        self.setWindowTitle("新增脚本" if script is None else "编辑脚本")
        self.resize(self.DIALOG_WIDTH, self.DIALOG_HEIGHT)
        self.setMinimumSize(self.DIALOG_WIDTH, self.DIALOG_HEIGHT)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入脚本名称")
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("选择要启动的程序或脚本")
        self.arguments_edit = QLineEdit()
        self.arguments_edit.setPlaceholderText("输入启动参数，可留空")
        self.run_timeout_spin = QSpinBox()
        self.run_timeout_spin.setRange(0, 24 * 60 * 60)
        self.run_timeout_spin.setSuffix(" 秒")
        self.run_timeout_spin.setSpecialValueText("不限制")
        self.run_timeout_spin.setValue(DEFAULT_RUN_TIMEOUT_SECONDS)
        self.monitor_process_name_edit = AnimatedComboBox()
        self.monitor_process_name_edit.setProperty("wideDropDownHitbox", True)
        self.monitor_process_name_edit.setEditable(True)
        self.monitor_process_name_edit.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.monitor_process_name_edit.setDuplicatesEnabled(False)
        if self.monitor_process_name_edit.lineEdit() is not None:
            self.monitor_process_name_edit.lineEdit().setPlaceholderText("输入游戏进程名")
        self._populate_monitor_process_combo()
        self.close_script_on_finish_switch = Switch()
        self.close_game_on_finish_switch = Switch()
        self.close_script_on_finish_switch.setChecked(True)
        self.close_game_on_finish_switch.setChecked(True)

        self.path_browse_button = QPushButton("浏览...")
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )

        self._build_layout()
        self._connect_signals()
        self._load_script()

    def _build_layout(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_2)

        form_card = QFrame(self)
        form_card.setObjectName("SettingsCard")
        form_card_layout = QVBoxLayout(form_card)
        form_card_layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        form_card_layout.setSpacing(0)

        form_layout = QFormLayout()
        form_layout.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        form_layout.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        form_layout.setHorizontalSpacing(SPACE_3)
        form_layout.setVerticalSpacing(SPACE_2)
        for label_text, field, hint_text in self._field_rows():
            form_layout.addRow(
                label_text,
                self._build_field_group(field, hint_text),
            )

        for label_text, toggle, hint_text in self._toggle_rows():
            form_layout.addRow(
                label_text,
                self._build_toggle_group(toggle, hint_text),
            )

        form_card_layout.addLayout(form_layout)

        layout.addWidget(form_card)
        layout.addWidget(self.button_box)
        apply_elevation(form_card, "card")

    def _field_rows(self) -> tuple[tuple[str, QWidget, str], ...]:
        return (
            ("脚本名称", self.name_edit, "用于显示脚本名称。"),
            ("程序路径", self._build_path_row(), "要启动的程序或脚本路径。"),
            ("启动参数", self.arguments_edit, "启动程序时附带的参数，可留空。"),
            ("日志超时", self.run_timeout_spin, "脚本无日志输出超时时间，0 表示不限制。"),
            (
                "监测游戏关闭进程",
                self.monitor_process_name_edit,
                "用于识别游戏进程，必填。",
            ),
        )

    def _toggle_rows(self) -> tuple[tuple[str, Switch, str], ...]:
        return (
            (
                "结束后关闭脚本",
                self.close_script_on_finish_switch,
                "任务结束后关闭脚本进程。",
            ),
            (
                "结束后关闭游戏",
                self.close_game_on_finish_switch,
                "任务结束后关闭游戏进程。",
            ),
        )

    def _build_path_row(self) -> QWidget:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_1)
        layout.addWidget(self.path_edit)
        layout.addWidget(self.path_browse_button)
        return container

    def _build_field_group(self, field: QWidget, hint_text: str) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_1)

        hint_label = QLabel(hint_text, container)
        hint_label.setObjectName("HintText")
        hint_label.setWordWrap(True)

        layout.addWidget(field)
        layout.addWidget(hint_label)
        return container

    def _build_toggle_group(self, toggle: Switch, hint_text: str) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_1)

        toggle_row = QHBoxLayout()
        toggle_row.setContentsMargins(0, 0, 0, 0)
        toggle_row.setSpacing(SPACE_1)

        state_label = QLabel("关闭", container)
        state_label.setObjectName("HintText")
        toggle.toggled.connect(
            lambda checked, label=state_label: label.setText("开启" if checked else "关闭")
        )

        toggle_row.addWidget(toggle)
        toggle_row.addWidget(state_label)
        toggle_row.addStretch(1)

        hint_label = QLabel(hint_text, container)
        hint_label.setObjectName("HintText")
        hint_label.setWordWrap(True)

        layout.addLayout(toggle_row)
        layout.addWidget(hint_label)
        return container

    def _connect_signals(self) -> None:
        self.path_browse_button.clicked.connect(self._browse_executable)
        self.monitor_process_name_edit.activated.connect(
            self._apply_monitor_process_preset_by_index
        )
        self.button_box.accepted.connect(self._validate_and_accept)
        self.button_box.rejected.connect(self.reject)

    def _populate_monitor_process_combo(self) -> None:
        self.monitor_process_name_edit.clear()
        for label, process_name in self.MONITOR_PROCESS_PRESETS:
            self.monitor_process_name_edit.addItem(label, process_name)
        self.monitor_process_name_edit.setCurrentIndex(-1)
        self.monitor_process_name_edit.setCurrentText("")

    def _load_script(self) -> None:
        if self._script is None:
            return

        self.name_edit.setText(self._script.name)
        self.path_edit.setText(self._script.executable_path)
        self.arguments_edit.setText(self._script.arguments)
        self.run_timeout_spin.setValue(max(0, self._script.run_timeout_seconds))
        self.monitor_process_name_edit.setCurrentText(self._script.monitor_process_name)
        self.close_script_on_finish_switch.setChecked(
            self._script.close_script_on_finish
        )
        self.close_game_on_finish_switch.setChecked(self._script.close_game_on_finish)

    def _browse_executable(self) -> None:
        selected_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择脚本或程序",
        )
        if selected_path:
            self.path_edit.setText(selected_path)

    def _apply_monitor_process_preset_by_index(self, index: int) -> None:
        process_name = str(self.monitor_process_name_edit.itemData(index) or "").strip()
        if not process_name:
            return
        self.monitor_process_name_edit.setCurrentText(process_name)
        self.monitor_process_name_edit.setFocus()

    def _validate_and_accept(self) -> None:
        name = self.name_edit.text().strip()
        executable_path = self.path_edit.text().strip()
        monitor_process_name = self.monitor_process_name_edit.currentText().strip()

        if not name:
            QMessageBox.warning(self, "缺少名称", "请先输入脚本名称。")
            return

        if not executable_path:
            QMessageBox.warning(self, "缺少路径", "请先选择程序路径。")
            return

        if not self._can_launch(executable_path):
            QMessageBox.warning(
                self,
                "路径不可用",
                "填写的程序路径不存在，也不是系统可直接调用的命令。",
            )
            return

        if not monitor_process_name:
            QMessageBox.warning(
                self,
                "缺少游戏进程",
                "请填写“监测游戏关闭进程”。",
            )
            return

        if self.close_game_on_finish_switch.isChecked() and not monitor_process_name:
            QMessageBox.warning(
                self,
                "缺少监测进程",
                "开启“结束后关闭游戏”时，请填写“监测游戏关闭进程”。",
            )
            return

        self.accept()

    def _can_launch(self, executable_path: str) -> bool:
        candidate = executable_path.strip().strip('"').strip("'")
        if not candidate:
            return False

        expanded_candidate = os.path.expandvars(candidate)
        if Path(expanded_candidate).expanduser().exists():
            return True

        return shutil.which(candidate) is not None

    def build_script(self) -> ScriptDefinition:
        payload = {
            "name": self.name_edit.text().strip(),
            "executable_path": self.path_edit.text().strip(),
            "arguments": self.arguments_edit.text().strip(),
            "script_process_name": "",
            "run_timeout_seconds": self.run_timeout_spin.value(),
            "monitor_process_name": self.monitor_process_name_edit.currentText().strip(),
            "completion_mode": CompletionMode.GAME_PROCESS,
            "close_script_on_finish": self.close_script_on_finish_switch.isChecked(),
            "close_game_on_finish": self.close_game_on_finish_switch.isChecked(),
            "enabled": True if self._script is None else self._script.enabled,
        }

        if self._script is None:
            return ScriptDefinition.create(**payload)

        return ScriptDefinition(
            script_id=self._script.script_id,
            **payload,
        )
