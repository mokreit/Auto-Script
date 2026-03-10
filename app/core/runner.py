from __future__ import annotations

import locale
import shlex
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from io import BufferedReader
from pathlib import Path
from queue import Empty, Queue
from time import monotonic

from PySide6.QtCore import QObject, QTimer, Signal

from app.core.models import (
    CompletionMode,
    ScriptDefinition,
    TaskStatus,
    coerce_completion_mode,
    format_timeout_seconds,
)

DEFAULT_TERMINATE_TIMEOUT_SECONDS = 3.0
POLL_INTERVAL_MS = 50
FORCE_KILL_GRACE_SECONDS = 0.5
MONITOR_WAIT_SECONDS = 30.0
MONITOR_CHECK_INTERVAL_SECONDS = 0.2


@dataclass(slots=True)
class ScriptRunContext:
    script: ScriptDefinition
    index: int
    total: int
    started_at: datetime | None = None
    ended_at: datetime | None = None
    exit_code: int | None = None
    status: TaskStatus = TaskStatus.PENDING
    message: str = ""
    timed_out: bool = False

    @property
    def duration_seconds(self) -> float | None:
        if self.started_at is None or self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()


class ScriptRunner(QObject):
    execution_state_changed = Signal(bool)
    execution_started = Signal(int)
    script_launching = Signal(object)
    script_started = Signal(object)
    script_output = Signal(object, str, str)
    script_finished = Signal(object)
    execution_finished = Signal(bool, str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_process)

        self._scripts: list[ScriptDefinition] = []
        self._current_index = -1
        self._current_context: ScriptRunContext | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._output_queue: Queue[tuple[str, str]] = Queue()
        self._reader_threads: list[threading.Thread] = []
        self._is_running = False
        self._stop_requested = False
        self._skip_requested = False
        self._had_failures = False
        self._stop_deadline: float | None = None
        self._continue_on_failure = True
        self._terminate_timeout_seconds = DEFAULT_TERMINATE_TIMEOUT_SECONDS
        self._script_timeout_seconds = 0.0
        self._timeout_deadline: float | None = None
        self._timeout_triggered = False
        self._close_script_on_finish = False
        self._close_game_on_finish = False
        self._script_close_requested = False
        self._game_close_requested = False
        self._script_process_name = ""
        self._game_process_name = ""
        self._completion_mode = CompletionMode.LAUNCH_PROCESS
        self._completion_process_name = ""
        self._completion_seen_running = False
        self._completion_completed = False
        self._completion_wait_deadline: float | None = None
        self._completion_check_next_at = 0.0
        self._completion_check_interval_seconds = MONITOR_CHECK_INTERVAL_SECONDS
        self._reader_threads_finalized = False
        self._preferred_encoding = locale.getpreferredencoding(False) or "utf-8"

    @property
    def is_running(self) -> bool:
        return self._is_running

    def start(
        self,
        scripts: list[ScriptDefinition],
        *,
        continue_on_failure: bool = True,
        terminate_timeout_seconds: float = 3.0,
    ) -> bool:
        if self._is_running or not scripts:
            return False

        self._reset_execution_state()
        self._scripts = list(scripts)
        self._continue_on_failure = continue_on_failure
        self._terminate_timeout_seconds = max(0.5, float(terminate_timeout_seconds))
        self._is_running = True

        self.execution_state_changed.emit(True)
        self.execution_started.emit(len(self._scripts))
        self._start_next_script()
        return True

    def update_runtime_settings(
        self,
        *,
        continue_on_failure: bool | None = None,
        terminate_timeout_seconds: float | None = None,
    ) -> None:
        if continue_on_failure is not None:
            self._continue_on_failure = bool(continue_on_failure)

        if terminate_timeout_seconds is not None:
            normalized_timeout = max(0.5, float(terminate_timeout_seconds))
            self._terminate_timeout_seconds = normalized_timeout
            if (
                self._process is not None
                and self._process.poll() is None
                and self._stop_deadline is not None
            ):
                self._stop_deadline = monotonic() + normalized_timeout

    def stop(self) -> bool:
        if not self._is_running or self._stop_requested or self._skip_requested:
            return False

        self._stop_requested = True
        if self._process is None or self._process.poll() is not None:
            self._finish_execution(False, "执行已停止。")
            return True

        if self._current_context is not None:
            self._emit_system_output(
                "正在关闭当前脚本..."
                if self._close_script_on_finish
                else "正在停止当前脚本...",
            )

        self._request_current_process_stop()
        return True

    def skip_current(self) -> bool:
        if not self._is_running or self._stop_requested or self._skip_requested:
            return False

        if self._current_context is None:
            return False

        if self._process is None:
            return False

        return_code = self._process.poll()
        if return_code is not None:
            if self._completion_process_name and not self._completion_completed:
                self._skip_requested = True
                self._emit_system_output("正在跳过当前脚本...")
                self._finalize_current_process(return_code)
                return True
            return False

        self._skip_requested = True
        self._emit_system_output("正在跳过当前脚本...")
        self._request_current_process_stop()
        return True

    def _start_next_script(self) -> None:
        if self._stop_requested:
            self._finish_execution(False, "执行已停止。")
            return

        self._current_index += 1
        if self._current_index >= len(self._scripts):
            if self._had_failures:
                self._finish_execution(False, "执行完成，但存在失败脚本。")
            else:
                self._finish_execution(True, "所有已开启脚本执行完成。")
            return

        script = self._scripts[self._current_index]
        self._current_context = ScriptRunContext(
            script=script,
            index=self._current_index + 1,
            total=len(self._scripts),
        )
        self._script_process_name = self._normalize_process_name(
            script.script_process_name
        )
        self._game_process_name = self._normalize_process_name(
            script.monitor_process_name
        )
        self._completion_mode = coerce_completion_mode(script.completion_mode)
        self._completion_process_name = self._resolve_completion_process_name()
        self._script_timeout_seconds = max(0.0, float(script.run_timeout_seconds))
        self._close_script_on_finish = script.close_script_on_finish
        self._close_game_on_finish = script.close_game_on_finish
        self._script_close_requested = False
        self._game_close_requested = False
        self._timeout_deadline = (
            monotonic() + self._script_timeout_seconds
            if self._script_timeout_seconds > 0
            else None
        )
        self._timeout_triggered = False
        self._completion_seen_running = False
        self._completion_completed = False
        self._completion_wait_deadline = None
        self._completion_check_next_at = 0.0
        self._reader_threads_finalized = False
        self.script_launching.emit(self._current_context)

        program = self._resolve_program(script.executable_path)
        arguments = self._parse_arguments(script.arguments)

        try:
            self._process = subprocess.Popen(
                [program, *arguments],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False,
                bufsize=0,
            )
        except OSError as exc:
            self._handle_start_failure(str(exc))
            return

        self._current_context.started_at = datetime.now()
        self._current_context.status = TaskStatus.RUNNING
        self._current_context.message = "运行中"
        self.script_started.emit(self._current_context)
        if self._script_process_name:
            self._emit_system_output(
                f"已配置脚本进程名: {self._script_process_name}。"
            )
        if self._game_process_name:
            self._emit_system_output(
                f"已启用游戏关闭监测: {self._game_process_name}。"
            )
        if self._completion_process_name:
            completion_target = (
                "脚本进程"
                if self._completion_mode is CompletionMode.SCRIPT_PROCESS
                else "游戏进程"
            )
            self._emit_system_output(
                f"完成判定: 等待{completion_target}关闭 {self._completion_process_name}。"
            )
        elif self._completion_mode is CompletionMode.LAUNCH_PROCESS:
            self._emit_system_output("完成判定: 启动进程退出。")
        elif self._current_context is not None:
            self._emit_system_output("完成判定: 未配置对应进程名，将按启动进程退出判定。")
        if self._script_timeout_seconds > 0:
            self._emit_system_output(
                "已启用运行超时检测: "
                f"{format_timeout_seconds(int(self._script_timeout_seconds))}。"
            )
        if self._close_script_on_finish:
            self._emit_system_output(
                "已启用结束后关闭脚本：任务结束时会优先关闭脚本进程名，未填写时关闭当前启动进程及子进程。"
            )
        if self._close_game_on_finish:
            self._emit_system_output(
                (
                    "已启用结束后关闭游戏：任务结束时会尝试关闭监测到的游戏进程。"
                    if self._game_process_name
                    else "已启用结束后关闭游戏，但当前未填写监测游戏关闭进程。"
                )
            )

        self._start_reader_threads()
        self._poll_timer.start()

    def _start_reader_threads(self) -> None:
        if self._process is None:
            return

        self._reader_threads = []
        for stream_name, pipe in (
            ("stdout", self._process.stdout),
            ("stderr", self._process.stderr),
        ):
            if pipe is None:
                continue

            thread = threading.Thread(
                target=self._read_stream,
                args=(stream_name, pipe),
                daemon=True,
            )
            thread.start()
            self._reader_threads.append(thread)

    def _read_stream(self, stream_name: str, pipe: BufferedReader) -> None:
        try:
            for line in iter(pipe.readline, b""):
                if not line:
                    break
                self._output_queue.put((stream_name, self._decode_output(line)))
        finally:
            pipe.close()

    def _poll_process(self) -> None:
        self._drain_output_queue()
        if self._process is None:
            return

        if (
            self._timeout_deadline is not None
            and not self._stop_requested
            and not self._skip_requested
            and not self._timeout_triggered
            and monotonic() >= self._timeout_deadline
        ):
            self._timeout_triggered = True
            if self._current_context is not None:
                self._current_context.timed_out = True
                self._emit_system_output(
                    "运行超时，正在关闭当前脚本..."
                    if self._close_script_on_finish
                    else "运行超时，正在结束当前脚本...",
                )

            # 超时后不再等待监控进程结果，但保留进程名以便执行结束动作。
            self._completion_seen_running = True
            self._completion_completed = True
            self._completion_wait_deadline = None
            self._completion_check_next_at = 0.0

            if self._process.poll() is None:
                self._request_current_process_stop()

        if self._stop_deadline is not None and monotonic() >= self._stop_deadline:
            if self._process.poll() is None:
                if self._current_context is not None:
                    timeout_message = (
                        "跳过超时，已强制结束当前脚本。"
                        if self._skip_requested
                        else "终止超时，已强制结束当前脚本。"
                    )
                    self._emit_system_output(timeout_message)
                self._process.kill()
            self._stop_deadline = None

        return_code = self._process.poll()

        if self._completion_process_name:
            self._poll_completion_process()
            if self._completion_completed and return_code is None:
                if self._stop_deadline is None:
                    self._emit_system_output(
                        "完成判定进程已结束，正在关闭当前脚本..."
                        if self._close_script_on_finish
                        else "完成判定进程已结束，正在结束当前脚本..."
                    )
                    self._request_current_process_stop()
                return

            if self._completion_seen_running and not self._completion_completed:
                if return_code is not None:
                    self._finalize_reader_threads()
                return

            if return_code is not None and not self._completion_seen_running:
                if self._completion_wait_deadline is None:
                    self._completion_wait_deadline = monotonic() + MONITOR_WAIT_SECONDS
                    self._emit_system_output(
                        "脚本进程已结束，正在等待完成判定进程启动或状态确认..."
                    )
                if monotonic() < self._completion_wait_deadline:
                    self._finalize_reader_threads()
                    return

        if return_code is None:
            return

        self._poll_timer.stop()
        self._finalize_reader_threads()
        self._finalize_current_process(return_code)

    def _finalize_current_process(self, return_code: int) -> None:
        if self._current_context is None:
            return

        current_context = self._current_context
        current_context.ended_at = datetime.now()
        current_context.exit_code = return_code
        skip_requested = self._skip_requested
        completion_completed = (
            self._completion_process_name and self._completion_completed
        )

        if skip_requested:
            current_context.status = TaskStatus.SKIPPED
            current_context.message = "已跳过"
        elif self._stop_requested:
            current_context.status = TaskStatus.STOPPED
            current_context.message = "已停止"
        elif current_context.timed_out:
            current_context.status = TaskStatus.FAILED
            current_context.message = "运行超时"
            self._had_failures = True
        elif completion_completed:
            current_context.status = TaskStatus.SUCCESS
            current_context.message = "完成判定进程已结束"
        elif return_code == 0:
            current_context.status = TaskStatus.SUCCESS
            current_context.message = "执行完成"
        else:
            current_context.status = TaskStatus.FAILED
            current_context.message = "异常退出"
            self._had_failures = True

        self._close_script_after_finish_if_needed()
        self._close_game_after_finish_if_needed()
        self.script_finished.emit(current_context)
        failure_message = (
            f"脚本 {current_context.script.name} 执行失败，队列已停止。"
        )
        stop_on_failure = (
            current_context.status is TaskStatus.FAILED
            and not self._continue_on_failure
        )
        self._current_context = None
        self._reset_process_runtime_state()
        self._skip_requested = False

        if self._stop_requested:
            self._finish_execution(False, "执行已停止。")
        elif stop_on_failure:
            self._finish_execution(False, failure_message)
        else:
            self._start_next_script()

    def _handle_start_failure(self, error_message: str) -> None:
        if self._current_context is None:
            return

        display_message = error_message
        if "WinError 740" in error_message:
            display_message = (
                "目标程序要求管理员权限。请以管理员身份启动调度器后重试。"
            )

        self._current_context.ended_at = datetime.now()
        self._current_context.exit_code = -1
        self._current_context.status = TaskStatus.FAILED
        self._current_context.message = "启动失败"
        self._had_failures = True
        self.script_output.emit(
            self._current_context,
            "system",
            f"启动失败: {display_message}",
        )
        self.script_finished.emit(self._current_context)
        failure_message = (
            f"脚本 {self._current_context.script.name} 启动失败，队列已停止。"
        )

        if self._stop_requested:
            self._finish_execution(False, "执行已停止。")
        elif not self._continue_on_failure:
            self._finish_execution(False, failure_message)
        else:
            self._start_next_script()

    def _drain_output_queue(self) -> None:
        if self._current_context is None:
            self._clear_output_queue()
            return

        while True:
            try:
                stream, text = self._output_queue.get_nowait()
            except Empty:
                break
            self.script_output.emit(self._current_context, stream, text)

    def _clear_output_queue(self) -> None:
        while True:
            try:
                self._output_queue.get_nowait()
            except Empty:
                break

    def _emit_system_output(self, message: str) -> None:
        if self._current_context is None:
            return
        self.script_output.emit(self._current_context, "system", message)

    def _resolve_completion_process_name(self) -> str:
        if self._completion_mode is CompletionMode.SCRIPT_PROCESS:
            return self._script_process_name
        if self._completion_mode is CompletionMode.GAME_PROCESS:
            return self._game_process_name
        return ""

    def _reset_process_runtime_state(self) -> None:
        self._process = None
        self._reader_threads = []
        self._stop_deadline = None
        self._script_timeout_seconds = 0.0
        self._timeout_deadline = None
        self._timeout_triggered = False
        self._close_script_on_finish = False
        self._close_game_on_finish = False
        self._script_close_requested = False
        self._game_close_requested = False
        self._script_process_name = ""
        self._game_process_name = ""
        self._completion_mode = CompletionMode.LAUNCH_PROCESS
        self._completion_process_name = ""
        self._completion_seen_running = False
        self._completion_completed = False
        self._completion_wait_deadline = None
        self._completion_check_next_at = 0.0
        self._reader_threads_finalized = False

    def _reset_execution_state(self) -> None:
        self._scripts = []
        self._current_index = -1
        self._current_context = None
        self._reset_process_runtime_state()
        self._stop_requested = False
        self._skip_requested = False
        self._had_failures = False
        self._continue_on_failure = True
        self._terminate_timeout_seconds = DEFAULT_TERMINATE_TIMEOUT_SECONDS
        self._clear_output_queue()

    def _request_current_process_stop(self) -> None:
        if self._process is None or self._process.poll() is not None:
            return

        if self._close_script_on_finish:
            if self._script_process_name and self._terminate_processes_by_image_name(
                self._script_process_name
            ):
                self._script_close_requested = True
                self._stop_deadline = monotonic() + FORCE_KILL_GRACE_SECONDS
                return
            if self._terminate_process_tree(self._process.pid):
                self._script_close_requested = True
                self._stop_deadline = monotonic() + FORCE_KILL_GRACE_SECONDS
                return

        self._process.terminate()
        self._stop_deadline = monotonic() + self._terminate_timeout_seconds

    def _close_script_after_finish_if_needed(self) -> None:
        if (
            not self._close_script_on_finish
            or self._script_close_requested
            or not self._script_process_name
        ):
            return

        if not self._is_process_running(self._script_process_name):
            self._script_close_requested = True
            return

        self._script_close_requested = True
        self._emit_system_output(
            f"任务结束，正在关闭脚本进程: {self._script_process_name}"
        )
        if self._terminate_processes_by_image_name(self._script_process_name):
            self._emit_system_output(
                f"已发送关闭脚本指令: {self._script_process_name}"
            )
            return

        self._emit_system_output(f"关闭脚本失败: {self._script_process_name}")

    def _close_game_after_finish_if_needed(self) -> None:
        if (
            not self._close_game_on_finish
            or not self._game_process_name
            or self._game_close_requested
        ):
            return

        if not self._is_process_running(self._game_process_name):
            self._game_close_requested = True
            return

        self._game_close_requested = True
        if self._current_context is not None:
            self._emit_system_output(
                f"任务结束，正在关闭游戏进程: {self._game_process_name}"
            )

        if self._terminate_processes_by_image_name(self._game_process_name):
            if self._current_context is not None:
                self._emit_system_output(
                    f"已发送关闭游戏指令: {self._game_process_name}"
                )
            return

        if self._current_context is not None:
            self._emit_system_output(f"关闭游戏失败: {self._game_process_name}")

    def _finish_execution(self, completed: bool, message: str) -> None:
        self._poll_timer.stop()
        self._reset_execution_state()

        if self._is_running:
            self._is_running = False
            self.execution_state_changed.emit(False)

        self.execution_finished.emit(completed, message)

    def _resolve_program(self, executable_path: str) -> str:
        candidate = executable_path.strip()
        if not candidate:
            return candidate

        candidate_path = Path(candidate)
        if candidate_path.is_absolute() or candidate_path.parent != Path("."):
            return str(candidate_path)

        resolved = shutil.which(candidate)
        return resolved or candidate

    def _parse_arguments(self, argument_string: str) -> list[str]:
        if not argument_string:
            return []

        try:
            parts = shlex.split(
                argument_string,
                posix=not sys.platform.startswith("win"),
            )
        except ValueError:
            return [argument_string]

        return [self._strip_quotes(part) for part in parts]

    def _strip_quotes(self, token: str) -> str:
        if len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'"}:
            return token[1:-1]
        return token

    def _finalize_reader_threads(self) -> None:
        if self._reader_threads_finalized:
            return

        for thread in self._reader_threads:
            thread.join(timeout=0.2)
        self._reader_threads = []
        self._reader_threads_finalized = True
        self._drain_output_queue()

    def _poll_completion_process(self) -> None:
        if not self._completion_process_name:
            return

        now = monotonic()
        if now < self._completion_check_next_at:
            return
        self._completion_check_next_at = now + self._completion_check_interval_seconds

        is_running = self._is_process_running(self._completion_process_name)
        if is_running:
            if not self._completion_seen_running and self._current_context is not None:
                self._emit_system_output(
                    f"检测到完成判定进程已启动: {self._completion_process_name}"
                )
            self._completion_seen_running = True
            return

        if self._completion_seen_running and not self._completion_completed:
            self._completion_completed = True
            if self._current_context is not None:
                self._emit_system_output(
                    f"完成判定进程已结束: {self._completion_process_name}"
                )

    def _normalize_process_name(self, process_name: str) -> str:
        value = process_name.strip().strip('"').strip("'")
        if not value:
            return ""

        filename = Path(value).name
        if sys.platform.startswith("win") and "." not in filename:
            return f"{filename}.exe"
        return filename

    def _is_process_running(self, process_name: str) -> bool:
        command = [
            "tasklist",
            "/FI",
            f"IMAGENAME eq {process_name}",
            "/FO",
            "CSV",
            "/NH",
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding=self._preferred_encoding,
                errors="ignore",
                creationflags=creationflags,
                check=False,
            )
        except OSError:
            return False

        if result.returncode != 0:
            return False

        expected_name = process_name.lower()
        for raw_line in result.stdout.splitlines():
            line = raw_line.strip()
            if not line or not line.startswith('"'):
                continue

            image_name = line.split('","', 1)[0].strip('"').strip().lower()
            if image_name == expected_name:
                return True
        return False

    def _terminate_process_tree(self, process_id: int) -> bool:
        if process_id <= 0:
            return False
        return self._run_taskkill(["/PID", str(process_id), "/T", "/F"])

    def _terminate_processes_by_image_name(self, process_name: str) -> bool:
        if not process_name:
            return False
        return self._run_taskkill(["/IM", process_name, "/T", "/F"])

    def _run_taskkill(self, arguments: list[str]) -> bool:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            result = subprocess.run(
                ["taskkill", *arguments],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding=self._preferred_encoding,
                errors="ignore",
                creationflags=creationflags,
                check=False,
            )
        except OSError:
            return False

        return result.returncode == 0

    def _decode_output(self, payload: bytes) -> str:
        if not payload:
            return ""

        encodings = [
            "utf-8",
            "utf-8-sig",
            self._preferred_encoding,
            "gb18030",
            "cp936",
        ]

        seen: set[str] = set()
        for encoding in encodings:
            normalized = encoding.lower()
            if normalized in seen:
                continue
            seen.add(normalized)

            try:
                return payload.decode(encoding)
            except UnicodeDecodeError:
                continue

        return payload.decode(self._preferred_encoding, errors="replace")
