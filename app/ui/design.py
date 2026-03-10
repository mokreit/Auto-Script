from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget

GRID_UNIT = 8
SPACE_1 = GRID_UNIT
SPACE_2 = GRID_UNIT * 2
SPACE_3 = GRID_UNIT * 3
SPACE_4 = GRID_UNIT * 4

_ELEVATION_TOKENS = {
    "sidebar": (36, 0, 14, QColor(10, 23, 37, 30)),
    "surface": (28, 0, 10, QColor(16, 24, 40, 20)),
    "card": (22, 0, 8, QColor(16, 24, 40, 18)),
    "floating": (26, 0, 10, QColor(16, 24, 40, 24)),
}


def apply_elevation(widget: QWidget, level: str = "card") -> None:
    blur_radius, offset_x, offset_y, color = _ELEVATION_TOKENS.get(
        level,
        _ELEVATION_TOKENS["card"],
    )
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur_radius)
    shadow.setOffset(offset_x, offset_y)
    shadow.setColor(color)
    widget.setGraphicsEffect(shadow)
