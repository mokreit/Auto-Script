from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPoint, QRectF, QSize, QVariantAnimation, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QCheckBox, QWidget


class Switch(QCheckBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(44, 24)
        self._margin = 3
        self._offset = self._handle_position(self.isChecked())

        self._animation = QVariantAnimation(self)
        self._animation.setDuration(180)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.valueChanged.connect(self._update_offset)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QSize:
        return QSize(44, 24)

    def hitButton(self, pos: QPoint) -> bool:
        return self.rect().contains(pos)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#d0d5dd"))

        track_rect = QRectF(0, 0, self.width(), self.height())
        track_color = QColor("#0f6cbd") if self.isChecked() else QColor("#f8fafc")
        painter.setBrush(track_color)
        painter.drawRoundedRect(track_rect, track_rect.height() / 2, track_rect.height() / 2)

        handle_diameter = self.height() - self._margin * 2
        handle_rect = QRectF(
            self._offset,
            self._margin,
            handle_diameter,
            handle_diameter,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(handle_rect)

    def _animate(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(self._handle_position(checked))
        self._animation.start()

    def _handle_position(self, checked: bool) -> float:
        diameter = self.height() - self._margin * 2
        if checked:
            return float(self.width() - diameter - self._margin)
        return float(self._margin)

    def _update_offset(self, value: float | int) -> None:
        self._offset = float(value)
        self.update()
