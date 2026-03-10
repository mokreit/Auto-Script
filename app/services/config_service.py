from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.core.models import (
    RunSettings,
    ScriptDefinition,
    build_sample_scripts,
)

DEFAULT_WINDOW_WIDTH = 1360
DEFAULT_WINDOW_HEIGHT = 860
MIN_WINDOW_WIDTH = 960
MIN_WINDOW_HEIGHT = 640


@dataclass(slots=True)
class AppConfig:
    scripts: list[ScriptDefinition]
    run_settings: RunSettings = field(default_factory=RunSettings)
    window_width: int = DEFAULT_WINDOW_WIDTH
    window_height: int = DEFAULT_WINDOW_HEIGHT


class ConfigService:
    def __init__(self, config_path: Path | None = None) -> None:
        if getattr(sys, "frozen", False):
            # When running as a PyInstaller bundle, use the executable's directory
            project_root = Path(sys.executable).parent
        else:
            # When running from source, use the project root
            project_root = Path(__file__).resolve().parents[2]

        self.config_path = config_path or project_root / "data" / "config.json"

    def load(self) -> tuple[AppConfig, bool]:
        payload = self._read_payload()
        if payload is None:
            return self._default_config(), False

        scripts = [
            script
            for item in payload.get("scripts", [])
            if (script := ScriptDefinition.from_payload(item)) is not None
        ]
        window_width, window_height = self._load_window_size(payload.get("window"))

        return AppConfig(
            scripts=scripts,
            run_settings=RunSettings.from_payload(payload.get("settings")),
            window_width=window_width,
            window_height=window_height,
        ), True

    def save(self, config: AppConfig) -> None:
        payload = {
            "scripts": [script.to_payload() for script in config.scripts],
            "settings": config.run_settings.to_payload(),
            "window": self._window_payload(
                config.window_width,
                config.window_height,
            ),
        }

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _default_config(self) -> AppConfig:
        return AppConfig(scripts=build_sample_scripts())

    def _read_payload(self) -> dict[str, object] | None:
        if not self.config_path.exists():
            return None

        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        if not isinstance(payload, dict):
            return None
        return payload

    def _load_window_size(self, payload: object) -> tuple[int, int]:
        if not isinstance(payload, dict):
            return DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT

        return (
            self._normalize_window_dimension(
                payload.get("width"),
                DEFAULT_WINDOW_WIDTH,
                MIN_WINDOW_WIDTH,
            ),
            self._normalize_window_dimension(
                payload.get("height"),
                DEFAULT_WINDOW_HEIGHT,
                MIN_WINDOW_HEIGHT,
            ),
        )

    def _window_payload(self, width: int, height: int) -> dict[str, int]:
        return {
            "width": self._normalize_window_dimension(
                width,
                DEFAULT_WINDOW_WIDTH,
                MIN_WINDOW_WIDTH,
            ),
            "height": self._normalize_window_dimension(
                height,
                DEFAULT_WINDOW_HEIGHT,
                MIN_WINDOW_HEIGHT,
            ),
        }

    def _normalize_window_dimension(
        self,
        value: object,
        fallback: int,
        minimum: int,
    ) -> int:
        return max(minimum, self._safe_int(value, fallback))

    def _safe_int(self, value: object, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback
