from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from functools import partial
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.models import (
    RunSettings,
    ScriptDefinition,
    TaskStatus,
    format_timeout_seconds,
)
from app.core.runner import ScriptRunContext, ScriptRunner
from app.services.config_service import AppConfig, ConfigService
from app.ui.design import SPACE_1, SPACE_2, SPACE_3, SPACE_4, apply_elevation
from app.ui.script_editor_dialog import ScriptEditorDialog
from app.ui.widgets.switch import Switch

DONATION_QR_PATH = Path(__file__).resolve().parent / "assets" / "wechat-appreciation.png"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.config_service = ConfigService()
        self.app_config, loaded_from_disk = self.config_service.load()
        self.scripts: list[ScriptDefinition] = self.app_config.scripts
        self.run_settings = self.app_config.run_settings
        self.runner = ScriptRunner(self)

        self._is_running = False
        self._current_script_id: str | None = None
        self._run_script_ids: list[str] = []
        self._current_run_index = 0
        self._current_run_total = 0
        self._run_started_at: datetime | None = None
        self._run_status_counts = self._create_empty_run_counts()
        self._last_run_result = "尚未执行"
        self._last_run_detail = "等待开始"

        self.setWindowTitle("Auto-Script")
        self.resize(self.app_config.window_width, self.app_config.window_height)

        self._build_ui()
        self._connect_signals()
        self._refresh_script_cards()
        self._switch_page(0, self.script_page_button, "脚本")

        if loaded_from_disk:
            self._append_log("应用已启动，已恢复本地配置。")
            self._update_status_widgets("已加载本地配置。")
        else:
            self._save_state()
            self._append_log("应用已启动，已生成默认示例配置。")
            self._update_status_widgets("已创建默认配置。")

    def _build_ui(self) -> None:
        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("执行阶段会在这里展示输出、状态和异常信息。")

        self.config_path_detail = self._build_readonly_line_edit()
        self.config_path_detail.setText(str(self.config_service.config_path))
        self.select_config_button = self._create_button("选择...", "ghost")
        self.window_size_detail = self._build_readonly_line_edit()
        self.continue_on_failure_checkbox = QCheckBox("异常后继续执行后续脚本")
        self.continue_on_failure_checkbox.setChecked(self.run_settings.continue_on_failure)
        self.auto_clear_log_checkbox = QCheckBox("开始执行时自动清空日志")
        self.auto_clear_log_checkbox.setChecked(self.run_settings.auto_clear_log_on_start)
        self.show_completion_dialog_checkbox = QCheckBox("执行结束后弹出结果提示")
        self.show_completion_dialog_checkbox.setChecked(
            self.run_settings.show_completion_dialog
        )
        self.terminate_timeout_spin = QSpinBox()
        self.terminate_timeout_spin.setRange(1, 30)
        self.terminate_timeout_spin.setSuffix(" 秒")
        self.terminate_timeout_spin.setValue(self.run_settings.terminate_timeout_seconds)
        self.terminate_timeout_spin.setMinimumWidth(120)

        self.add_script_button = self._create_button("新增脚本", "primary")
        self.start_button = self._create_button("开始执行", "primary")
        self.stop_button = self._create_button("停止执行", "ghost")
        self.skip_button = self._create_button("跳过当前", "ghost")
        self.clear_log_button = self._create_button("清空日志", "ghost")

        self.run_summary_result_label = QLabel()
        self.run_summary_result_label.setObjectName("RunSummaryResult")
        self.run_summary_counts_label = QLabel()
        self.run_summary_counts_label.setObjectName("RunSummaryMeta")
        self.run_summary_duration_label = QLabel()
        self.run_summary_duration_label.setObjectName("RunSummaryMeta")
        self.run_summary_mode_label = QLabel()
        self.run_summary_mode_label.setObjectName("RunSummaryMeta")
        self.run_summary_detail_label = QLabel()
        self.run_summary_detail_label.setObjectName("HintText")
        self.run_summary_detail_label.setWordWrap(True)

        self.script_page_button = self._create_button("脚本", "nav", checkable=True)
        self.settings_page_button = self._create_button("设置", "nav", checkable=True)
        self.donate_page_button = self._create_button("赞赏", "nav", checkable=True)
        self.about_page_button = self._create_button("关于", "nav", checkable=True)
        self.page_stack = QStackedWidget()

        self.script_summary_label = QLabel()
        self.script_summary_label.setObjectName("SummaryPillValue")
        self.script_mode_label = QLabel()
        self.script_mode_label.setObjectName("SummaryPillValue")

        self.script_cards_container = QWidget(self)
        self.script_cards_layout = QVBoxLayout(self.script_cards_container)
        self.script_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.script_cards_layout.setSpacing(SPACE_1)

        self.script_scroll_area = QScrollArea(self)
        self.script_scroll_area.setWidgetResizable(True)
        self.script_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.script_scroll_area.setWidget(self.script_cards_container)
        self.main_splitter: QSplitter | None = None
        self.log_panel: QFrame | None = None

        central_widget = QWidget(self)
        central_widget.setObjectName("AppShell")
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_2)
        root_layout.setSpacing(SPACE_3)
        root_layout.addWidget(self._build_main_splitter())

        self.setCentralWidget(central_widget)
        self._build_status_bar()
        self._update_settings_details()
        self._update_run_summary_card()

    def _build_readonly_line_edit(self) -> QLineEdit:
        widget = QLineEdit()
        widget.setReadOnly(True)
        return widget

    def _build_config_path_row(self) -> QWidget:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_2)
        layout.addWidget(self.config_path_detail, 1)
        layout.addWidget(self.select_config_button)
        return container

    def _create_button(
        self,
        text: str,
        role: str,
        *,
        checkable: bool = False,
    ) -> QPushButton:
        button = QPushButton(text)
        button.setCheckable(checkable)
        button.setProperty("role", role)
        return button

    def _connect_page_button(
        self,
        button: QPushButton,
        page_index: int,
        page_title: str,
    ) -> None:
        button.clicked.connect(
            lambda _checked=False, current_button=button, current_index=page_index, current_title=page_title: self._switch_page(
                current_index,
                current_button,
                current_title,
            )
        )

    def _connect_run_settings_inputs(self) -> None:
        for signal in (
            self.continue_on_failure_checkbox.stateChanged,
            self.auto_clear_log_checkbox.stateChanged,
            self.show_completion_dialog_checkbox.stateChanged,
            self.terminate_timeout_spin.valueChanged,
        ):
            signal.connect(self._handle_run_settings_changed)

    def _build_main_splitter(self) -> QSplitter:
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self._build_left_workspace())
        self.main_splitter.addWidget(self._build_log_panel())
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 7)
        self.main_splitter.setSizes(self._default_splitter_sizes())
        return self.main_splitter

    def _default_splitter_sizes(self) -> list[int]:
        width = max(1200, self.width())
        return [
            max(360, width * 25 // 100),
            max(840, width * 75 // 100),
        ]

    def _build_left_workspace(self) -> QWidget:
        self.page_stack.addWidget(self._build_scripts_page())
        self.page_stack.addWidget(self._build_settings_page())
        self.page_stack.addWidget(self._build_donation_page())
        self.page_stack.addWidget(self._build_about_page())

        workspace = QWidget(self)
        layout = QHBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_3)
        layout.addWidget(self._build_function_panel())
        layout.addWidget(self.page_stack, 1)
        return workspace

    def _build_function_panel(self) -> QFrame:
        panel = QFrame(self)
        panel.setObjectName("FunctionPanel")
        panel.setMaximumWidth(160)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_2)

        brand_title = QLabel("脚本调度器")
        brand_title.setObjectName("BrandTitle")
        brand_caption = QLabel("顺序执行脚本")
        brand_caption.setObjectName("BrandCaption")

        layout.addWidget(brand_title)
        layout.addWidget(brand_caption)
        layout.addSpacing(SPACE_2)
        layout.addWidget(self.script_page_button)
        layout.addWidget(self.settings_page_button)
        layout.addStretch(1)
        layout.addWidget(self.donate_page_button)
        layout.addWidget(self.about_page_button)
        apply_elevation(panel, "sidebar")
        return panel

    def _build_scripts_page(self) -> QFrame:
        page = QFrame(self)
        page.setObjectName("PageSurface")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(SPACE_4, SPACE_4, SPACE_4, SPACE_4)
        layout.setSpacing(SPACE_3)

        layout.addWidget(self._build_scripts_overview_card())
        layout.addWidget(self.script_scroll_area, 1)
        return page

    def _build_scripts_overview_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("HeroCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_2)

        eyebrow_label = QLabel("队列")
        eyebrow_label.setObjectName("SectionMeta")

        title_label = QLabel("流程队列")
        title_label.setObjectName("HeroTitle")

        description_label = QLabel("按顺序运行已启用脚本。")
        description_label.setObjectName("HeroText")
        description_label.setWordWrap(True)

        header_row = QHBoxLayout()
        header_row.setSpacing(SPACE_2)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(SPACE_1)
        text_layout.addWidget(eyebrow_label)
        text_layout.addWidget(title_label)
        text_layout.addWidget(description_label)

        header_row.addLayout(text_layout, 1)
        header_row.addWidget(self.add_script_button, 0, Qt.AlignmentFlag.AlignTop)

        metric_row = QHBoxLayout()
        metric_row.setSpacing(SPACE_2)
        metric_row.addWidget(self._build_summary_pill("概览", self.script_summary_label))
        metric_row.addWidget(self._build_summary_pill("策略", self.script_mode_label))
        metric_row.addStretch(1)

        layout.addLayout(header_row)
        layout.addLayout(metric_row)
        apply_elevation(card, "surface")
        return card

    def _build_summary_pill(self, title: str, value_label: QLabel) -> QFrame:
        pill = QFrame(self)
        pill.setObjectName("SummaryPill")

        layout = QVBoxLayout(pill)
        layout.setContentsMargins(SPACE_2, SPACE_2, SPACE_2, SPACE_2)
        layout.setSpacing(SPACE_1)

        title_label = QLabel(title)
        title_label.setObjectName("SummaryPillTitle")

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        return pill

    def _build_settings_page(self) -> QFrame:
        page = QFrame(self)
        page.setObjectName("PageSurface")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(SPACE_4, SPACE_4, SPACE_4, SPACE_4)
        layout.setSpacing(SPACE_3)

        title = QLabel("设置")
        title.setObjectName("PageTitle")

        base_settings_card = QFrame(self)
        base_settings_card.setObjectName("SettingsCard")
        base_form_layout = QFormLayout(base_settings_card)
        base_form_layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        base_form_layout.setSpacing(SPACE_2)
        base_form_layout.addRow("配置文件", self._build_config_path_row())
        base_form_layout.addRow("窗口尺寸", self.window_size_detail)

        runtime_settings_card = QFrame(self)
        runtime_settings_card.setObjectName("SettingsCard")
        runtime_form_layout = QFormLayout(runtime_settings_card)
        runtime_form_layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        runtime_form_layout.setSpacing(SPACE_2)
        runtime_form_layout.addRow("终止等待", self.terminate_timeout_spin)
        runtime_form_layout.addRow("", self.continue_on_failure_checkbox)
        runtime_form_layout.addRow("", self.auto_clear_log_checkbox)
        runtime_form_layout.addRow("", self.show_completion_dialog_checkbox)

        hint_label = QLabel(
            "这些设置会自动保存。首版先保留最必要的执行策略，避免界面变得过重。"
        )
        hint_label.setObjectName("HintText")
        hint_label.setWordWrap(True)
        runtime_form_layout.addRow("", hint_label)

        layout.addWidget(title)
        layout.addWidget(base_settings_card)
        layout.addWidget(runtime_settings_card)
        layout.addStretch(1)
        apply_elevation(base_settings_card, "card")
        apply_elevation(runtime_settings_card, "card")
        return page

    def _build_about_page(self) -> QFrame:
        page = QFrame(self)
        page.setObjectName("PageSurface")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(SPACE_4, SPACE_4, SPACE_4, SPACE_4)
        layout.setSpacing(SPACE_3)

        title = QLabel("关于")
        title.setObjectName("PageTitle")

        intro_label = QLabel(
            "这是一个面向 Windows 的通用脚本调度工具，目标是把多个外部程序串起来执行，减少手动切换和盯进程的成本。"
        )
        intro_label.setObjectName("HintText")
        intro_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(intro_label)
        for section_title, description in self._about_sections():
            layout.addWidget(self._build_about_card(section_title, description))
        layout.addStretch(1)
        return page

    def _about_sections(self) -> tuple[tuple[str, str], ...]:
        return (
            (
                "项目定位",
                (
                    "Auto-Script聚焦“简单可用”的本地桌面场景。"
                    "你可以把常用工具、游戏脚本或辅助程序加入队列，按顺序执行，并在右侧实时查看运行日志。"
                ),
            ),
            (
                "当前能力",
                (
                    "支持脚本新增、编辑、删除、启用开关、顺序调整、串行执行、"
                    "超时检测、游戏关闭监测、结束后关闭脚本/游戏，以及本地配置自动保存。"
                ),
            ),
            (
                "使用方式",
                (
                    "先在“脚本”页添加任务并配置启动参数，再按需要设置超时、监测进程和结束动作。"
                    "点击“开始执行”后，程序会按当前顺序依次运行所有已开启脚本，并给出本轮执行摘要。"
                ),
            ),
            (
                "技术信息",
                (
                    "当前版本基于 Python 3.12 与 PySide6 构建，配置文件默认保存在 "
                    f"{self.config_service.config_path}。"
                ),
            ),
        )

    def _build_donation_page(self) -> QFrame:
        page = QFrame(self)
        page.setObjectName("PageSurface")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(SPACE_4, SPACE_4, SPACE_4, SPACE_4)
        layout.setSpacing(SPACE_3)

        title = QLabel("赞赏")
        title.setObjectName("PageTitle")

        hint_label = QLabel("这是微信赞赏码。")
        hint_label.setObjectName("HintText")
        hint_label.setWordWrap(True)

        card = QFrame(self)
        card.setObjectName("SettingsCard")
        card.setMaximumWidth(420)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        card_layout.setSpacing(SPACE_2)

        meta_label = QLabel("微信赞赏码")
        meta_label.setObjectName("SectionMeta")
        meta_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        qr_label = QLabel(card)
        qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        qr_pixmap = QPixmap(str(DONATION_QR_PATH))
        if qr_pixmap.isNull():
            qr_label.setText("赞赏码图片未找到。")
            qr_label.setObjectName("HintText")
        else:
            qr_label.setPixmap(
                qr_pixmap.scaled(
                    320,
                    320,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        caption_label = QLabel("微信扫码即可赞赏支持。")
        caption_label.setObjectName("HintText")
        caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        caption_label.setWordWrap(True)

        card_layout.addWidget(meta_label)
        card_layout.addWidget(qr_label)
        card_layout.addWidget(caption_label)

        layout.addWidget(title)
        layout.addWidget(hint_label)
        layout.addStretch(1)
        layout.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)
        apply_elevation(card, "card")
        return page

    def _build_about_card(self, title: str, description: str) -> QFrame:
        card = QFrame(self)
        card.setObjectName("SettingsCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_1)

        title_label = QLabel(title)
        title_label.setObjectName("SectionMeta")

        description_label = QLabel(description)
        description_label.setObjectName("HintText")
        description_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(description_label)
        apply_elevation(card, "card")
        return card

    def _build_log_panel(self) -> QFrame:
        panel = QFrame(self)
        panel.setObjectName("LogPanel")
        self.log_panel = panel

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_2)

        title = QLabel("运行日志")
        title.setObjectName("LogPanelTitle")
        caption = QLabel("实时输出与状态")
        caption.setObjectName("LogCaption")
        caption.setWordWrap(False)

        header_row = QHBoxLayout()
        header_row.setSpacing(SPACE_2)

        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(SPACE_1)
        header_text_layout.addWidget(title)
        header_text_layout.addWidget(caption)

        header_row.addLayout(header_text_layout, 1)
        header_row.addWidget(self._build_run_control_panel(), 0, Qt.AlignmentFlag.AlignTop)

        layout.addLayout(header_row)
        layout.addWidget(self._build_run_summary_card())
        layout.addWidget(self.log_output, 1)
        apply_elevation(panel, "surface")
        return panel

    def _build_run_summary_card(self) -> QFrame:
        card = QFrame(self)
        card.setObjectName("RunSummaryCard")

        layout = QGridLayout(card)
        layout.setContentsMargins(SPACE_2, SPACE_1, SPACE_2, SPACE_1)
        layout.setHorizontalSpacing(SPACE_1)
        layout.setVerticalSpacing(SPACE_1)

        summary_title = QLabel("本轮执行摘要")
        summary_title.setObjectName("SectionMeta")

        layout.addWidget(summary_title, 0, 0, 1, 2)
        layout.addWidget(self.run_summary_result_label, 1, 0, 1, 2)
        layout.addWidget(self.run_summary_counts_label, 2, 0)
        layout.addWidget(self.run_summary_duration_label, 2, 1)
        layout.addWidget(self.run_summary_mode_label, 3, 0, 1, 2)
        layout.addWidget(self.run_summary_detail_label, 4, 0, 1, 2)
        apply_elevation(card, "card")
        return card

    def _build_run_control_panel(self) -> QFrame:
        panel = QFrame(self)
        panel.setObjectName("ControlPanel")

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(SPACE_1, SPACE_1, SPACE_1, SPACE_1)
        layout.setSpacing(SPACE_1)
        for button in (
            self.start_button,
            self.stop_button,
            self.skip_button,
            self.clear_log_button,
        ):
            button.setProperty("compact", True)
        layout.addWidget(self.start_button)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.skip_button)
        layout.addStretch(1)
        layout.addWidget(self.clear_log_button)
        apply_elevation(panel, "card")
        return panel

    def _build_status_bar(self) -> None:
        self.current_task_label = QLabel("运行状态: 待机")
        self.next_task_label = QLabel("待执行: 无")
        self.progress_label = QLabel("脚本数: 0 | 已开启: 0")

        status_bar = self.statusBar()
        status_bar.addPermanentWidget(self.current_task_label)
        status_bar.addPermanentWidget(self.next_task_label)
        status_bar.addPermanentWidget(self.progress_label)

    def _connect_signals(self) -> None:
        for button, handler in (
            (self.add_script_button, self._add_script),
            (self.start_button, self._handle_start_requested),
            (self.stop_button, self._handle_stop_requested),
            (self.skip_button, self._handle_skip_requested),
            (self.clear_log_button, self._clear_log),
        ):
            button.clicked.connect(handler)
        self.select_config_button.clicked.connect(self._select_config_file)

        for button, page_index, page_title in (
            (self.script_page_button, 0, "脚本"),
            (self.settings_page_button, 1, "设置"),
            (self.donate_page_button, 2, "赞赏"),
            (self.about_page_button, 3, "关于"),
        ):
            self._connect_page_button(button, page_index, page_title)

        self.runner.execution_state_changed.connect(self._handle_runner_state_changed)
        self.runner.execution_started.connect(self._handle_execution_started)
        self.runner.script_launching.connect(self._handle_script_launching)
        self.runner.script_started.connect(self._handle_script_started)
        self.runner.script_output.connect(self._handle_script_output)
        self.runner.script_finished.connect(self._handle_script_finished)
        self.runner.execution_finished.connect(self._handle_execution_finished)

        self._connect_run_settings_inputs()

    def _refresh_script_cards(self) -> None:
        self._clear_layout(self.script_cards_layout)
        enabled_count = len(self._enabled_scripts())

        summary = f"{len(self.scripts)} 脚本 / {enabled_count} 启用"
        if self._is_running and self._current_run_total:
            summary = f"{summary} / {self._current_run_index}/{self._current_run_total}"
        self.script_summary_label.setText(summary)
        self.script_mode_label.setText(self._queue_mode_text())

        if not self.scripts:
            empty_label = QLabel("还没有脚本，点击右上角新增。")
            empty_label.setObjectName("EmptyState")
            empty_label.setWordWrap(True)
            self.script_cards_layout.addWidget(empty_label)
            self.script_cards_layout.addStretch(1)
            self._update_control_state()
            return

        for index, script in enumerate(self.scripts):
            self.script_cards_layout.addWidget(self._build_script_card(script, index))

        self.script_cards_layout.addStretch(1)
        self._update_control_state()

    def _build_script_card(self, script: ScriptDefinition, index: int) -> QFrame:
        card = QFrame(self)
        card.setObjectName("ScriptCard")
        card.setProperty("active", script.enabled)
        card.setProperty(
            "current",
            self._is_running and script.script_id == self._current_script_id,
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(SPACE_2, SPACE_2, SPACE_2, SPACE_2)
        layout.setSpacing(SPACE_1)

        header_row = QHBoxLayout()
        header_row.setSpacing(SPACE_1)

        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(SPACE_1)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(SPACE_1)
        badge_row.addWidget(self._create_tag_label(f"#{index + 1:02d}", "accent"))
        badge_row.addWidget(self._script_state_tag(script))
        badge_row.addStretch(1)

        title = QLabel(script.name)
        title.setObjectName("ScriptName")

        toggle_button = Switch(card)
        self._apply_toggle_state(toggle_button, script.enabled)
        toggle_button.setEnabled(not self._is_running)
        toggle_button.toggled.connect(
            lambda checked, current_script_id=script.script_id: self._toggle_script_enabled(
                current_script_id,
                checked,
            )
        )

        header_text_layout.addLayout(badge_row)
        header_text_layout.addWidget(title)

        header_row.addLayout(header_text_layout, 1)
        header_row.addStretch(1)
        header_row.addWidget(toggle_button)

        chip_row = QHBoxLayout()
        chip_row.setSpacing(SPACE_1)
        for chip_text, tone in self._script_tags(script):
            chip_row.addWidget(self._create_tag_label(chip_text, tone))
        chip_row.addStretch(1)

        action_row = QHBoxLayout()
        action_row.setSpacing(SPACE_1)
        for button in (
            self._create_script_action_button(
                "上移",
                "ghost",
                enabled=not self._is_running and index > 0,
                handler=partial(self._move_script, script.script_id, -1),
            ),
            self._create_script_action_button(
                "下移",
                "ghost",
                enabled=not self._is_running and index < len(self.scripts) - 1,
                handler=partial(self._move_script, script.script_id, 1),
            ),
            self._create_script_action_button(
                "编辑",
                "ghost",
                enabled=not self._is_running,
                handler=partial(self._edit_script, script.script_id),
            ),
            self._create_script_action_button(
                "删除",
                "danger",
                enabled=not self._is_running,
                handler=partial(self._delete_script, script.script_id),
            ),
        ):
            action_row.addWidget(button)
        action_row.addStretch(1)

        layout.addLayout(header_row)
        layout.addLayout(chip_row)
        layout.addLayout(action_row)
        apply_elevation(card, "card")
        return card

    def _apply_toggle_state(self, button: Switch, is_enabled: bool) -> None:
        button.setChecked(is_enabled)

    def _create_tag_label(self, text: str, tone: str = "neutral") -> QLabel:
        label = QLabel(text)
        label.setObjectName("TagLabel")
        label.setProperty("tone", tone)
        return label

    def _script_state_tag(self, script: ScriptDefinition) -> QLabel:
        if self._is_running and script.script_id == self._current_script_id:
            return self._create_tag_label("当前", "success")
        return self._create_tag_label("启用" if script.enabled else "停用", "neutral")

    def _create_script_action_button(
        self,
        text: str,
        role: str,
        *,
        enabled: bool,
        handler: Callable[[], None],
    ) -> QPushButton:
        button = self._create_button(text, role)
        button.setProperty("compact", True)
        button.setEnabled(enabled)
        button.clicked.connect(handler)
        return button

    def _script_tags(self, script: ScriptDefinition) -> list[tuple[str, str]]:
        tags = [
            (
                f"超时 {format_timeout_seconds(script.run_timeout_seconds)}"
                if script.run_timeout_seconds > 0
                else "不限时",
                "neutral",
            ),
        ]

        finish_actions = self._script_finish_actions(script)
        if finish_actions:
            tags.append((f"结束后 {' / '.join(finish_actions)}", "warn"))
        else:
            tags.append(("结束后 无操作", "muted"))
        return tags

    def _script_finish_actions(self, script: ScriptDefinition) -> list[str]:
        actions: list[str] = []
        if script.close_script_on_finish:
            actions.append("关脚本")
        if script.close_game_on_finish:
            actions.append("关游戏")
        return actions

    def _toggle_script_enabled(self, script_id: str, is_enabled: bool) -> None:
        script = self._get_script(script_id)
        if script is None:
            return

        script.enabled = is_enabled
        self._commit_script_changes(
            f"{script.name} 已切换为{'开启' if is_enabled else '关闭'}状态。",
            "脚本运行开关已更新。",
        )

    def _clear_layout(self, layout: QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()

            if widget is not None:
                widget.deleteLater()
            elif child_layout is not None:
                self._clear_layout(child_layout)

    def _commit_script_changes(self, log_message: str, status_message: str) -> None:
        self._refresh_script_cards()
        self._save_state()
        self._append_log(log_message)
        self._update_status_widgets(status_message)

    def _update_control_state(self) -> None:
        has_enabled_scripts = bool(self._enabled_scripts())
        self.add_script_button.setEnabled(not self._is_running)
        self.start_button.setEnabled(not self._is_running and has_enabled_scripts)
        self.stop_button.setEnabled(self._is_running)
        self.skip_button.setEnabled(self._is_running)
        self.select_config_button.setEnabled(not self._is_running)
        self.continue_on_failure_checkbox.setEnabled(True)
        self.auto_clear_log_checkbox.setEnabled(True)
        self.show_completion_dialog_checkbox.setEnabled(True)
        self.terminate_timeout_spin.setEnabled(True)

    def _get_script(self, script_id: str) -> ScriptDefinition | None:
        script_index = self._get_script_index(script_id)
        if script_index < 0:
            return None
        return self.scripts[script_index]

    def _get_script_index(self, script_id: str) -> int:
        return next(
            (index for index, script in enumerate(self.scripts) if script.script_id == script_id),
            -1,
        )

    def _enabled_scripts(self) -> list[ScriptDefinition]:
        return [script for script in self.scripts if script.enabled]

    def _create_empty_run_counts(self) -> dict[TaskStatus, int]:
        return {
            TaskStatus.SUCCESS: 0,
            TaskStatus.FAILED: 0,
            TaskStatus.SKIPPED: 0,
            TaskStatus.STOPPED: 0,
        }

    def _handle_run_settings_changed(self, *_args: object) -> None:
        self.run_settings = RunSettings(
            continue_on_failure=self.continue_on_failure_checkbox.isChecked(),
            auto_clear_log_on_start=self.auto_clear_log_checkbox.isChecked(),
            show_completion_dialog=self.show_completion_dialog_checkbox.isChecked(),
            terminate_timeout_seconds=self.terminate_timeout_spin.value(),
        )
        self.runner.update_runtime_settings(
            continue_on_failure=self.run_settings.continue_on_failure,
            terminate_timeout_seconds=float(self.run_settings.terminate_timeout_seconds),
        )
        self.script_mode_label.setText(self._queue_mode_text())
        self._save_state()
        self._update_run_summary_card()
        self.statusBar().showMessage(
            "运行设置已更新，并立即应用。"
            if self._is_running
            else "运行设置已更新。",
            4000,
        )

    def _run_mode_text(self) -> str:
        failure_mode = "异常后继续" if self.run_settings.continue_on_failure else "异常即停止"
        clear_mode = (
            "启动时清空日志"
            if self.run_settings.auto_clear_log_on_start
            else "保留历史日志"
        )
        dialog_mode = (
            "完成后弹窗"
            if self.run_settings.show_completion_dialog
            else "完成后不弹窗"
        )
        return (
            f"{failure_mode} | 终止等待 {self.run_settings.terminate_timeout_seconds} 秒"
            f" | {clear_mode} | {dialog_mode}"
        )

    def _queue_mode_text(self) -> str:
        failure_mode = "继续" if self.run_settings.continue_on_failure else "停止"
        clear_mode = "清日志" if self.run_settings.auto_clear_log_on_start else "留日志"
        dialog_mode = "弹窗" if self.run_settings.show_completion_dialog else "静默"
        return (
            f"失败{failure_mode} | {self.run_settings.terminate_timeout_seconds}s"
            f" | {clear_mode} | {dialog_mode}"
        )

    def _update_run_summary_card(
        self,
        result_text: str | None = None,
        detail_text: str | None = None,
    ) -> None:
        if result_text is not None:
            self._last_run_result = result_text
        if detail_text is not None:
            self._last_run_detail = detail_text

        counts_text = (
            f"成功 {self._run_status_counts[TaskStatus.SUCCESS]}  |  "
            f"失败 {self._run_status_counts[TaskStatus.FAILED]}  |  "
            f"跳过 {self._run_status_counts[TaskStatus.SKIPPED]}  |  "
            f"停止 {self._run_status_counts[TaskStatus.STOPPED]}"
        )
        if self._run_started_at is None:
            duration_text = "耗时: -"
        else:
            elapsed_seconds = max(
                0.0,
                (datetime.now() - self._run_started_at).total_seconds(),
            )
            duration_text = f"耗时: {elapsed_seconds:.1f}s"

        summary_state = self._summary_state_name()
        self.run_summary_result_label.setProperty("state", summary_state)
        self.run_summary_result_label.setText(self._last_run_result)
        self.run_summary_counts_label.setText(counts_text)
        self.run_summary_duration_label.setText(duration_text)
        self.run_summary_mode_label.setText(self._run_mode_text())
        self.run_summary_detail_label.setText(self._last_run_detail)
        self._refresh_widget_style(self.run_summary_result_label)

    def _summary_state_name(self) -> str:
        if self._is_running:
            return "running"
        if self._run_status_counts[TaskStatus.STOPPED] > 0:
            return "stopped"
        if self._run_status_counts[TaskStatus.FAILED] > 0:
            return "warning" if self.run_settings.continue_on_failure else "failed"
        if self._run_status_counts[TaskStatus.SKIPPED] > 0:
            return "skipped"
        if self._run_status_counts[TaskStatus.SUCCESS] > 0:
            return "success"
        return "idle"

    def _execution_result_text(self, completed: bool) -> str:
        if self._run_status_counts[TaskStatus.STOPPED] > 0:
            return "已手动停止"
        if self._run_status_counts[TaskStatus.FAILED] > 0:
            return "执行完成但有失败" if completed else "失败后已停止"
        if self._run_status_counts[TaskStatus.SKIPPED] > 0:
            return "执行完成（含跳过）"
        if completed:
            return "全部成功"
        return "执行结束"

    def _show_completion_feedback(self, completed: bool, message: str) -> None:
        if not self.run_settings.show_completion_dialog:
            return

        if self._run_status_counts[TaskStatus.FAILED] > 0 or not completed:
            QMessageBox.warning(self, "执行结果", message)
            return

        QMessageBox.information(self, "执行结果", message)

    def _move_script(self, script_id: str, offset: int) -> None:
        if self._is_running:
            return

        source_index = self._get_script_index(script_id)
        if source_index < 0:
            return

        target_index = source_index + offset
        if target_index < 0 or target_index >= len(self.scripts):
            return

        script = self.scripts[source_index]
        self.scripts[source_index], self.scripts[target_index] = (
            self.scripts[target_index],
            self.scripts[source_index],
        )
        self._commit_script_changes(
            f"已调整顺序: {script.name} -> 第 {target_index + 1} 位。",
            "脚本执行顺序已更新。",
        )

    def _add_script(self) -> None:
        dialog = ScriptEditorDialog(self)
        if dialog.exec() != ScriptEditorDialog.DialogCode.Accepted:
            return

        script = dialog.build_script()
        self.scripts.append(script)
        self._commit_script_changes(
            f"已新增脚本: {script.name}",
            "脚本已新增。",
        )

    def _edit_script(self, script_id: str) -> None:
        script = self._get_script(script_id)
        if script is None:
            return

        dialog = ScriptEditorDialog(self, script=script)
        if dialog.exec() != ScriptEditorDialog.DialogCode.Accepted:
            return

        updated_script = dialog.build_script()
        script_index = self._get_script_index(updated_script.script_id)
        if script_index < 0:
            return

        self.scripts[script_index] = updated_script
        self._commit_script_changes(
            f"已更新脚本: {updated_script.name}",
            "脚本配置已更新。",
        )

    def _delete_script(self, script_id: str) -> None:
        script = self._get_script(script_id)
        if script is None:
            return

        result = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除脚本“{script.name}”吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return

        self.scripts = [item for item in self.scripts if item.script_id != script_id]
        self._commit_script_changes(
            f"已删除脚本: {script.name}",
            "脚本已删除。",
        )

    def _handle_start_requested(self) -> None:
        enabled_scripts = self._enabled_scripts()
        if not enabled_scripts:
            QMessageBox.information(
                self,
                "没有可运行脚本",
                "请先新增脚本，或把脚本切换到“开启”状态。",
            )
            return

        if self.runner.is_running:
            return

        if self.run_settings.auto_clear_log_on_start:
            self.log_output.clear()

        self._run_script_ids = [script.script_id for script in enabled_scripts]
        self._current_run_index = 0
        self._current_run_total = len(enabled_scripts)
        self._run_started_at = None
        self._run_status_counts = self._create_empty_run_counts()
        self._update_run_summary_card("准备执行", f"本轮计划执行 {len(enabled_scripts)} 个脚本。")
        self._append_log(f"准备执行 {len(enabled_scripts)} 个已开启脚本。")

        if not self.runner.start(
            enabled_scripts,
            continue_on_failure=self.run_settings.continue_on_failure,
            terminate_timeout_seconds=float(self.run_settings.terminate_timeout_seconds),
        ):
            QMessageBox.warning(self, "无法开始执行", "当前已有执行任务，或没有可运行脚本。")

    def _handle_stop_requested(self) -> None:
        if not self.runner.is_running:
            QMessageBox.information(self, "未在执行", "当前没有运行中的脚本任务。")
            return

        self.runner.stop()

    def _handle_skip_requested(self) -> None:
        if not self.runner.is_running:
            QMessageBox.information(self, "未在执行", "当前没有可跳过的运行中脚本。")
            return

        if self.runner.skip_current():
            return

        self.statusBar().showMessage("当前脚本暂时无法跳过。", 4000)

    def _handle_runner_state_changed(self, is_running: bool) -> None:
        self._is_running = is_running
        self._refresh_script_cards()
        self._update_run_summary_card()
        self._update_status_widgets()

    def _handle_execution_started(self, total: int) -> None:
        self._current_run_total = total
        self._current_run_index = 0
        self._run_started_at = datetime.now()
        self._run_status_counts = self._create_empty_run_counts()
        self._update_run_summary_card("执行中", f"队列已开始，共 {total} 个脚本。")
        self._update_status_widgets(f"执行已开始，共 {total} 个脚本。")

    def _handle_script_launching(self, context: ScriptRunContext) -> None:
        self._current_script_id = context.script.script_id
        self._current_run_index = context.index
        self._refresh_script_cards()
        self._update_status_widgets()

    def _handle_script_started(self, context: ScriptRunContext) -> None:
        self._append_log(
            f"开始执行 ({context.index}/{context.total}): {context.script.name}"
        )
        self._update_run_summary_card(detail_text=f"当前执行: {context.script.name}")
        self._update_status_widgets(f"正在执行: {context.script.name}")

    def _handle_script_output(
        self,
        context: ScriptRunContext,
        stream: str,
        text: str,
    ) -> None:
        stream_prefix = {
            "stdout": "OUT",
            "stderr": "ERR",
            "system": "SYS",
        }.get(stream, "LOG")

        for line in self._split_lines(text):
            self._append_log(f"[{context.script.name}][{stream_prefix}] {line}")

    def _handle_script_finished(self, context: ScriptRunContext) -> None:
        if context.status in self._run_status_counts:
            self._run_status_counts[context.status] += 1
        duration_text = (
            f"{context.duration_seconds:.1f}s"
            if context.duration_seconds is not None
            else "-"
        )
        exit_code_text = str(context.exit_code) if context.exit_code is not None else "-"
        self._append_log(
            f"{context.script.name} {context.status.value}，退出码 {exit_code_text}，耗时 {duration_text}。"
        )
        self._update_run_summary_card(detail_text=f"最近结果: {context.script.name} {context.status.value}")

    def _handle_execution_finished(self, completed: bool, message: str) -> None:
        self._current_script_id = None
        self._run_script_ids = []
        self._current_run_index = 0
        self._current_run_total = 0
        result_text = self._execution_result_text(completed)
        self._refresh_script_cards()
        self._append_log(message)
        self._update_run_summary_card(result_text, message)
        self._update_status_widgets(message)
        self._show_completion_feedback(completed, message)

    def _clear_log(self) -> None:
        self.log_output.clear()
        self.statusBar().showMessage("日志已清空。", 4000)

    def _select_config_file(self) -> None:
        if self._is_running:
            QMessageBox.information(self, "无法切换配置", "请先停止当前执行任务。")
            return

        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "选择配置文件",
            str(self.config_service.config_path),
            "JSON 文件 (*.json);;所有文件 (*.*)",
        )
        if not selected_path:
            return

        config_path = Path(selected_path).expanduser()
        if not config_path.suffix:
            config_path = config_path.with_suffix(".json")
        self._switch_config_file(config_path)

    def _switch_config_file(self, config_path: Path) -> bool:
        next_service = ConfigService(config_path)
        config_exists = next_service.config_path.exists()

        if config_exists:
            loaded_config, loaded_from_disk = next_service.load()
            if not loaded_from_disk:
                QMessageBox.warning(
                    self,
                    "配置读取失败",
                    "所选配置文件无法读取，已保留当前配置。",
                )
                return False

            self.config_service = next_service
            self._apply_loaded_config(loaded_config, resize_window=True)
            self._append_log(f"已切换配置文件: {self.config_service.config_path}")
            self._append_log("已加载所选配置文件。")
            self._update_status_widgets("已加载所选配置文件。")
            return True

        self.config_service = next_service
        self._save_state()
        self._append_log(f"已切换配置文件: {self.config_service.config_path}")
        self._update_status_widgets("已切换配置文件并保存当前配置。")
        return True

    def _apply_loaded_config(self, config: AppConfig, *, resize_window: bool) -> None:
        self.app_config = config
        self.scripts = config.scripts
        self.run_settings = config.run_settings
        self._sync_run_settings_controls()
        self.runner.update_runtime_settings(
            continue_on_failure=self.run_settings.continue_on_failure,
            terminate_timeout_seconds=float(self.run_settings.terminate_timeout_seconds),
        )
        if resize_window:
            self.resize(config.window_width, config.window_height)
        self._refresh_script_cards()
        self._update_settings_details()
        self._update_run_summary_card()

    def _sync_run_settings_controls(self) -> None:
        control_values = (
            (self.continue_on_failure_checkbox, self.run_settings.continue_on_failure),
            (self.auto_clear_log_checkbox, self.run_settings.auto_clear_log_on_start),
            (self.show_completion_dialog_checkbox, self.run_settings.show_completion_dialog),
        )
        for control, value in control_values:
            signals_blocked = control.blockSignals(True)
            control.setChecked(value)
            control.blockSignals(signals_blocked)

        spin_signals_blocked = self.terminate_timeout_spin.blockSignals(True)
        self.terminate_timeout_spin.setValue(self.run_settings.terminate_timeout_seconds)
        self.terminate_timeout_spin.blockSignals(spin_signals_blocked)

    def _update_status_widgets(self, message: str | None = None) -> None:
        enabled_scripts = self._enabled_scripts()

        if self._is_running:
            current_name = self._current_script_name()
            next_name = self._next_run_script_name()
            progress_text = (
                f"运行状态: 执行中 {self._current_run_index}/{self._current_run_total}"
                if self._current_run_total
                else "运行状态: 准备执行"
            )
            self.current_task_label.setText(progress_text)
            self.next_task_label.setText(f"当前脚本: {current_name}")
            self.progress_label.setText(f"下一项: {next_name}")
        else:
            next_script_name = enabled_scripts[0].name if enabled_scripts else "无"
            self.current_task_label.setText("运行状态: 待机")
            self.next_task_label.setText(f"待执行: {next_script_name}")
            self.progress_label.setText(
                f"脚本数: {len(self.scripts)} | 已开启: {len(enabled_scripts)}"
            )

        self._update_control_state()

        if message:
            self.statusBar().showMessage(message, 5000)

    def _current_script_name(self) -> str:
        if self._current_script_id is None:
            return "无"
        script = self._get_script(self._current_script_id)
        return script.name if script is not None else "无"

    def _next_run_script_name(self) -> str:
        if not self._run_script_ids or self._current_run_index >= len(self._run_script_ids):
            return "无"

        next_script = self._get_script(self._run_script_ids[self._current_run_index])
        return next_script.name if next_script is not None else "无"

    def _split_lines(self, text: str) -> list[str]:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        return [line for line in normalized.split("\n") if line]

    def _append_log(self, message: str) -> None:
        for line in self._split_lines(message):
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_output.appendPlainText(f"[{timestamp}] {line}")

    def _refresh_widget_style(self, widget: QWidget) -> None:
        style = widget.style()
        style.unpolish(widget)
        style.polish(widget)
        widget.update()

    def _update_settings_details(self) -> None:
        self.config_path_detail.setText(str(self.config_service.config_path))
        self.window_size_detail.setText(f"{self.width()} x {self.height()}")

    def _set_log_panel_visible(self, visible: bool) -> None:
        if self.log_panel is None or self.main_splitter is None:
            return

        self.log_panel.setVisible(visible)
        if visible:
            self.main_splitter.setSizes(self._default_splitter_sizes())
            return

        self.main_splitter.setSizes([max(1000, self.width()), 0])

    def _switch_page(self, index: int, selected_button: QPushButton, page_name: str) -> None:
        self.page_stack.setCurrentIndex(index)
        self._set_log_panel_visible(index == 0)

        for button in (
            self.script_page_button,
            self.settings_page_button,
            self.donate_page_button,
            self.about_page_button,
        ):
            button.setChecked(button is selected_button)
            self._refresh_widget_style(button)

        self.statusBar().showMessage(f"已切换到{page_name}页面。", 3000)

    def _save_state(self) -> None:
        config = AppConfig(
            scripts=self.scripts.copy(),
            run_settings=self.run_settings,
            window_width=self.width(),
            window_height=self.height(),
        )
        self.app_config = config
        self.config_service.save(config)
        self._update_settings_details()

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._update_settings_details()
        super().resizeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.runner.is_running:
            self.runner.stop()
        self._save_state()
        super().closeEvent(event)
