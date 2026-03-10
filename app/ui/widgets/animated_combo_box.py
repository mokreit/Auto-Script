from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QRect,
    QPropertyAnimation,
    QParallelAnimationGroup,
    Qt,
)
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsOpacityEffect,
    QListView,
    QWidget,
)


class NoWheelListView(QListView):
    def wheelEvent(self, event) -> None:  # type: ignore[override]
        event.ignore()


class AnimatedComboBox(QComboBox):
    DEFAULT_DROP_DOWN_HITBOX_WIDTH = 24
    WIDE_DROP_DOWN_HITBOX_WIDTH = 40
    POPUP_OFFSET_Y = 8
    POPUP_ANIMATION_OFFSET_Y = 10
    POPUP_ANIMATION_DURATION_MS = 160
    POPUP_ITEM_MIN_HEIGHT = 32
    POPUP_ITEM_SPACING_Y = 4
    POPUP_PADDING_Y = 24
    POPUP_MIN_HEIGHT = 88

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        popup_view = NoWheelListView(self)
        popup_view.setObjectName("ComboPopupView")
        self.setView(popup_view)
        self._popup_animation: QParallelAnimationGroup | None = None
        self._popup_opacity_effect = QGraphicsOpacityEffect(popup_view)
        self._popup_opacity_effect.setOpacity(1.0)
        popup_view.setGraphicsEffect(self._popup_opacity_effect)
        self._configure_popup_view()
        self._configure_popup_container()

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        event.ignore()

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if (
            self.isEnabled()
            and event.button() == Qt.MouseButton.LeftButton
            and self._is_drop_down_hit(event.position().toPoint())
        ):
            if self.view().isVisible():
                self.hidePopup()
            else:
                self.showPopup()
            event.accept()
            return
        super().mousePressEvent(event)

    def showPopup(self) -> None:
        self._stop_popup_animation()
        self._configure_popup_view()
        self._configure_popup_container()
        super().showPopup()
        self._configure_popup_view()

        popup = self._popup_container()
        if popup is None:
            return

        target_rect = self._popup_target_rect()
        popup_view_rect = self._popup_view_rect(target_rect)
        start_rect = self._popup_start_rect(target_rect)

        popup.setGeometry(target_rect)
        self._resize_popup_view(popup_view_rect)
        self.view().setGeometry(start_rect)
        self._popup_opacity_effect.setOpacity(0.0)
        popup.show()
        popup.raise_()
        self._animate_popup_open(start_rect, popup_view_rect)

    def hidePopup(self) -> None:
        self._stop_popup_animation()
        self._popup_opacity_effect.setOpacity(1.0)
        super().hidePopup()

    def _popup_container(self) -> QFrame | None:
        popup = self.view().window()
        if isinstance(popup, QFrame):
            return popup
        parent_popup = self.view().parentWidget()
        if isinstance(parent_popup, QFrame):
            return parent_popup
        return None

    def _configure_popup_container(self) -> None:
        popup = self._popup_container()
        if popup is None:
            return

        popup.setObjectName("ComboPopupContainer")
        popup.setFrameShape(QFrame.Shape.NoFrame)
        popup.setLineWidth(0)
        popup.setMidLineWidth(0)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        popup.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        popup.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)

    def _configure_popup_view(self) -> None:
        popup_view = self.view()
        popup_view.setUniformItemSizes(True)
        popup_view.setSpacing(self.POPUP_ITEM_SPACING_Y)
        popup_view.setAutoScroll(False)
        popup_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        popup_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def _drop_down_hitbox_width(self) -> int:
        if self.property("wideDropDownHitbox") is True:
            return self.WIDE_DROP_DOWN_HITBOX_WIDTH
        return self.DEFAULT_DROP_DOWN_HITBOX_WIDTH

    def _is_drop_down_hit(self, point: QPoint) -> bool:
        return point.x() >= self.width() - self._drop_down_hitbox_width()

    def _popup_target_rect(self) -> QRect:
        anchor = self.mapToGlobal(QPoint(0, self.height() + self.POPUP_OFFSET_Y))
        screen = QGuiApplication.screenAt(anchor) or QGuiApplication.primaryScreen()
        if screen is None:
            return QRect(anchor.x(), anchor.y(), self.width(), self.POPUP_MIN_HEIGHT)

        screen_geometry = screen.availableGeometry()
        width = self.width()
        content_height = self._popup_content_height()
        available_height = max(
            self.POPUP_MIN_HEIGHT,
            screen_geometry.bottom() - anchor.y() - self.POPUP_OFFSET_Y,
        )
        height = min(content_height, available_height)

        x = min(anchor.x(), screen_geometry.right() - width)
        x = max(screen_geometry.left(), x)
        y = max(anchor.y(), screen_geometry.top())
        return QRect(x, y, width, height)

    def _popup_content_height(self) -> int:
        visible_count = min(self.count(), max(1, self.maxVisibleItems()))
        row_height = max(
            self.POPUP_ITEM_MIN_HEIGHT,
            *(
                self.view().sizeHintForRow(index)
                for index in range(visible_count)
            ),
        )
        rows_height = (
            row_height * visible_count
            + self.view().spacing() * max(0, visible_count - 1)
        )
        return max(self.POPUP_MIN_HEIGHT, rows_height + self.POPUP_PADDING_Y)

    def _popup_view_rect(self, target_rect: QRect) -> QRect:
        return QRect(0, 0, target_rect.width(), target_rect.height())

    def _popup_start_rect(self, target_rect: QRect) -> QRect:
        popup_view_rect = self._popup_view_rect(target_rect)
        return popup_view_rect.translated(0, -self.POPUP_ANIMATION_OFFSET_Y)

    def _resize_popup_view(self, rect: QRect) -> None:
        self.view().setGeometry(0, 0, rect.width(), rect.height())

    def _animate_popup_open(
        self,
        start_rect: QRect,
        target_rect: QRect,
    ) -> None:
        geometry_animation = QPropertyAnimation(self.view(), b"geometry", self)
        geometry_animation.setDuration(self.POPUP_ANIMATION_DURATION_MS)
        geometry_animation.setStartValue(start_rect)
        geometry_animation.setEndValue(target_rect)
        geometry_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        opacity_animation = QPropertyAnimation(self._popup_opacity_effect, b"opacity", self)
        opacity_animation.setDuration(self.POPUP_ANIMATION_DURATION_MS)
        opacity_animation.setStartValue(0.0)
        opacity_animation.setEndValue(1.0)
        opacity_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

        animation_group = QParallelAnimationGroup(self)
        animation_group.addAnimation(geometry_animation)
        animation_group.addAnimation(opacity_animation)
        animation_group.finished.connect(
            lambda: self._finish_popup_animation(target_rect)
        )
        self._popup_animation = animation_group
        animation_group.start()

    def _finish_popup_animation(self, target_rect: QRect) -> None:
        self._popup_opacity_effect.setOpacity(1.0)
        self._resize_popup_view(target_rect)
        self.view().setGeometry(target_rect)
        self._popup_animation = None

    def _stop_popup_animation(self) -> None:
        if self._popup_animation is None:
            return
        self._popup_animation.stop()
        self._popup_animation = None
