from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

DEFAULT_RUN_TIMEOUT_SECONDS = 10 * 60
MAX_RUN_TIMEOUT_SECONDS = 24 * 60 * 60
MIN_TERMINATE_TIMEOUT_SECONDS = 1
MAX_TERMINATE_TIMEOUT_SECONDS = 30


class TaskStatus(StrEnum):
    PENDING = "未开始"
    RUNNING = "运行中"
    SUCCESS = "成功结束"
    FAILED = "异常结束"
    SKIPPED = "已跳过"
    STOPPED = "已停止"


class CompletionMode(StrEnum):
    LAUNCH_PROCESS = "launch_process"
    SCRIPT_PROCESS = "script_process"
    GAME_PROCESS = "game_process"


@dataclass(slots=True)
class RunSettings:
    continue_on_failure: bool = True
    auto_clear_log_on_start: bool = True
    show_completion_dialog: bool = False
    terminate_timeout_seconds: int = 3

    @classmethod
    def from_payload(cls, payload: object) -> "RunSettings":
        if not isinstance(payload, dict):
            return cls()

        return cls(
            continue_on_failure=bool(payload.get("continue_on_failure", True)),
            auto_clear_log_on_start=bool(payload.get("auto_clear_log_on_start", True)),
            show_completion_dialog=bool(payload.get("show_completion_dialog", False)),
            terminate_timeout_seconds=clamp_terminate_timeout_seconds(
                payload.get("terminate_timeout_seconds")
            ),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "continue_on_failure": self.continue_on_failure,
            "auto_clear_log_on_start": self.auto_clear_log_on_start,
            "show_completion_dialog": self.show_completion_dialog,
            "terminate_timeout_seconds": clamp_terminate_timeout_seconds(
                self.terminate_timeout_seconds
            ),
        }


@dataclass(slots=True)
class ScriptDefinition:
    script_id: str
    name: str
    executable_path: str
    arguments: str = ""
    script_process_name: str = ""
    monitor_process_name: str = ""
    completion_mode: CompletionMode = CompletionMode.LAUNCH_PROCESS
    run_timeout_seconds: int = DEFAULT_RUN_TIMEOUT_SECONDS
    close_script_on_finish: bool = False
    close_game_on_finish: bool = False
    enabled: bool = True

    @classmethod
    def create(
        cls,
        *,
        name: str,
        executable_path: str,
        arguments: str = "",
        script_process_name: str = "",
        monitor_process_name: str = "",
        completion_mode: CompletionMode | str = CompletionMode.LAUNCH_PROCESS,
        run_timeout_seconds: int = DEFAULT_RUN_TIMEOUT_SECONDS,
        close_script_on_finish: bool = False,
        close_game_on_finish: bool = False,
        enabled: bool = True,
    ) -> "ScriptDefinition":
        return cls(
            script_id=uuid4().hex,
            name=name,
            executable_path=executable_path,
            arguments=arguments,
            script_process_name=script_process_name,
            monitor_process_name=monitor_process_name,
            completion_mode=coerce_completion_mode(completion_mode),
            run_timeout_seconds=clamp_run_timeout_seconds(run_timeout_seconds),
            close_script_on_finish=bool(close_script_on_finish),
            close_game_on_finish=bool(close_game_on_finish),
            enabled=enabled,
        )

    @classmethod
    def from_payload(cls, payload: object) -> "ScriptDefinition | None":
        if not isinstance(payload, dict):
            return None

        script_id = str(payload.get("script_id", "")).strip()
        name = str(payload.get("name", "")).strip()
        executable_path = str(payload.get("executable_path", "")).strip()

        if not script_id or not name or not executable_path:
            return None

        return cls(
            script_id=script_id,
            name=name,
            executable_path=executable_path,
            arguments=str(payload.get("arguments", "")),
            script_process_name=str(payload.get("script_process_name") or ""),
            monitor_process_name=str(payload.get("monitor_process_name") or ""),
            completion_mode=completion_mode_from_payload(payload),
            run_timeout_seconds=clamp_run_timeout_seconds(
                payload.get("run_timeout_seconds")
            ),
            close_script_on_finish=bool(payload.get("close_script_on_finish", False)),
            close_game_on_finish=bool(payload.get("close_game_on_finish", False)),
            enabled=bool(payload.get("enabled", True)),
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "script_id": self.script_id,
            "name": self.name,
            "executable_path": self.executable_path,
            "arguments": self.arguments,
            "script_process_name": self.script_process_name,
            "monitor_process_name": self.monitor_process_name,
            "completion_mode": coerce_completion_mode(self.completion_mode).value,
            "run_timeout_seconds": clamp_run_timeout_seconds(self.run_timeout_seconds),
            "close_script_on_finish": self.close_script_on_finish,
            "close_game_on_finish": self.close_game_on_finish,
            "enabled": self.enabled,
        }


def clamp_run_timeout_seconds(value: object) -> int:
    try:
        timeout_seconds = int(value)
    except (TypeError, ValueError):
        timeout_seconds = DEFAULT_RUN_TIMEOUT_SECONDS

    return max(0, min(MAX_RUN_TIMEOUT_SECONDS, timeout_seconds))


def clamp_terminate_timeout_seconds(value: object) -> int:
    try:
        timeout_seconds = int(value)
    except (TypeError, ValueError):
        timeout_seconds = RunSettings().terminate_timeout_seconds

    return max(
        MIN_TERMINATE_TIMEOUT_SECONDS,
        min(MAX_TERMINATE_TIMEOUT_SECONDS, timeout_seconds),
    )


def coerce_completion_mode(value: CompletionMode | str | object) -> CompletionMode:
    if isinstance(value, CompletionMode):
        return value

    try:
        return CompletionMode(str(value))
    except ValueError:
        return CompletionMode.LAUNCH_PROCESS


def completion_mode_label(mode: CompletionMode | str | object) -> str:
    normalized_mode = coerce_completion_mode(mode)
    if normalized_mode is CompletionMode.LAUNCH_PROCESS:
        return "启动进程退出"
    if normalized_mode is CompletionMode.SCRIPT_PROCESS:
        return "脚本进程关闭"
    return "游戏进程关闭"


def completion_mode_from_payload(payload: dict[str, object]) -> CompletionMode:
    if "completion_mode" in payload:
        return coerce_completion_mode(payload.get("completion_mode"))

    if str(payload.get("monitor_process_name") or "").strip():
        return CompletionMode.GAME_PROCESS
    return CompletionMode.LAUNCH_PROCESS


def format_timeout_seconds(seconds: int) -> str:
    if seconds <= 0:
        return "不限制"
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"{seconds} 秒（{minutes} 分钟）"
    return f"{seconds} 秒"


def build_sample_scripts() -> list[ScriptDefinition]:
    project_root = Path(__file__).resolve().parents[2]
    sample_script = project_root / "examples" / "sample_echo.ps1"

    return [
        ScriptDefinition.create(
            name="PowerShell Echo",
            executable_path="powershell.exe",
            arguments=f'-ExecutionPolicy Bypass -File "{sample_script}" -Message "Hello from scheduler"',
        ),
        ScriptDefinition.create(
            name="Notepad Demo",
            executable_path="notepad.exe",
        ),
    ]
