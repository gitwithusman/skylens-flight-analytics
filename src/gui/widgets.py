"""Reusable building blocks shared by all pages."""

from __future__ import annotations

from typing import Callable, List, Optional

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from src import config, palette as P, visualizations

from . import icons
from .theme import SP_LG, SP_MD, SP_SM, SP_XL, repolish


class Card(QFrame):
    """White surface with a thin border (the only container style used)."""

    def __init__(self, parent=None, margins=(SP_LG, SP_MD + 2, SP_LG, SP_LG),
                 spacing: int = SP_MD):
        super().__init__(parent)
        self.setObjectName("card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*margins)
        self.body.setSpacing(spacing)

    def add_title(self, text: str, note: str = "") -> QLabel:
        title = QLabel(text)
        title.setObjectName("cardTitle")
        self.body.addWidget(title)
        if note:
            sub = QLabel(note)
            sub.setObjectName("cardNote")
            sub.setWordWrap(True)
            self.body.addWidget(sub)
        return title


class KpiCard(Card):
    """Metric tile: label, value, supporting note and a colour accent."""

    def __init__(self, label: str, accent: str = P.COBALT, parent=None):
        super().__init__(parent, margins=(0, 0, 0, 0), spacing=0)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.body.addLayout(row)
        bar = QFrame()
        bar.setObjectName("kpiBar")
        bar.setStyleSheet(f"background: {accent};")
        row.addWidget(bar)
        col = QVBoxLayout()
        col.setContentsMargins(SP_LG, SP_MD + 2, SP_LG, SP_MD + 2)
        col.setSpacing(2)
        row.addLayout(col, 1)
        self.label = QLabel(label)
        self.label.setObjectName("kpiLabel")
        self.value = QLabel("\u2013")
        self.value.setObjectName("kpiValue")
        self.note = QLabel("")
        self.note.setObjectName("kpiNote")
        self.note.setWordWrap(True)
        for w in (self.label, self.value, self.note):
            col.addWidget(w)
        self.setMinimumHeight(92)

    def set_value(self, value, note: str = "") -> None:
        self.value.setText(str(value))
        self.note.setText(note)
        self.value.setToolTip(str(value))


class ResponsiveGrid(QWidget):
    """Grid that re-flows its children into fewer/more columns on resize."""

    def __init__(self, min_item_width: int = 240, max_columns: int = 4,
                 spacing: int = SP_MD + 2, parent=None):
        super().__init__(parent)
        self._min_w, self._max_cols, self._spacing = min_item_width, max_columns, spacing
        self._items: List[QWidget] = []
        self._cols = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(spacing)

    def add(self, widget: QWidget) -> QWidget:
        self._items.append(widget)
        self._reflow(force=True)
        return widget

    def columns(self) -> int:
        return self._cols

    def _wanted_columns(self) -> int:
        width = max(self.width(), 1)
        fit = (width + self._spacing) // (self._min_w + self._spacing)
        n = len(self._items) or 1
        cols = max(1, min(self._max_cols, n, int(fit)))
        if cols >= 3:
            # avoid an orphan card on the last row (5 -> 3+2, 4 -> 2+2, 6 -> 3+3)
            options = range(cols, max(cols - 2, 1) - 1, -1)
            cols = min(options, key=lambda c: ((-n) % c, -c))
        return cols

    def _reflow(self, force: bool = False) -> None:
        cols = self._wanted_columns()
        if cols == self._cols and not force:
            return
        self._cols = cols
        for w in self._items:
            self._grid.removeWidget(w)
        for i, w in enumerate(self._items):
            self._grid.addWidget(w, i // cols, i % cols)
        for c in range(self._max_cols + 1):
            self._grid.setColumnStretch(c, 1 if c < cols else 0)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._reflow()


class ChartCard(Card):
    """Card holding one Matplotlib canvas plus a 'Save PNG' action."""

    def __init__(self, chart_key: str, title: str, min_height: int = 280,
                 parent=None):
        super().__init__(parent, margins=(SP_LG, SP_MD, SP_LG, SP_MD), spacing=SP_SM)
        self.chart_key = chart_key
        self._df: Optional[pd.DataFrame] = None
        self._canvas: Optional[FigureCanvasQTAgg] = None
        self._min_h = min_height
        head = QHBoxLayout()
        self._title = QLabel(title)
        self._title.setObjectName("cardTitle")
        self._save = QPushButton("Save PNG")
        self._save.setObjectName("subtle")
        self._save.setIcon(icons.icon("download", P.COBALT_DARK, size=16))
        self._save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save.setToolTip("Save this chart as a PNG image")
        self._save.clicked.connect(self._save_png)
        head.addWidget(self._title, 1)
        head.addWidget(self._save)
        self.body.addLayout(head)
        self._holder = QVBoxLayout()
        self._holder.setContentsMargins(0, 0, 0, 0)
        self.body.addLayout(self._holder, 1)
        self.setMinimumHeight(min_height + 56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def render(self, df: pd.DataFrame) -> None:
        self._df = df
        figure = visualizations.build_chart(self.chart_key, df, with_title=False)
        if self._canvas is not None:
            self._holder.removeWidget(self._canvas)
            self._canvas.hide()
            self._canvas.deleteLater()
        self._canvas = FigureCanvasQTAgg(figure)
        self._canvas.setMinimumHeight(self._min_h)
        self._canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._holder.addWidget(self._canvas)
        self._save.setEnabled(df is not None and not df.empty)

    def _save_png(self) -> None:
        if self._df is None:
            return
        main = self.window()
        notify = getattr(main, "notify", None)
        default = str(config.VISUALIZATIONS_DIR / f"{self.chart_key}.png")
        path, _ = QFileDialog.getSaveFileName(self, "Save chart", default, "PNG image (*.png)")
        if not path:
            return
        try:
            fig = visualizations.build_chart(self.chart_key, self._df, with_title=True)
            fig.savefig(path, dpi=150, facecolor=visualizations.SAVE_BG)
            if notify:
                notify(f"Chart saved to {path}", "success")
        except Exception as exc:  # disk full, permission denied, ...
            if notify:
                notify(f"Could not save the chart: {exc}", "error")


class EmptyState(Card):
    """Friendly placeholder shown when there is nothing to display yet."""

    def __init__(self, title: str, body: str, action_text: str = "",
                 action: Optional[Callable] = None, parent=None):
        super().__init__(parent, margins=(64, 32, 64, 32), spacing=SP_MD)
        pic = QLabel()
        pic.setPixmap(icons.pixmap("inbox", P.COBALT, 40))
        pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t = QLabel(title)
        t.setObjectName("emptyTitle")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b = QLabel(body)
        b.setObjectName("emptyBody")
        b.setAlignment(Qt.AlignmentFlag.AlignCenter)
        b.setWordWrap(True)
        for w in (pic, t, b):
            self.body.addWidget(w)
        if action_text and action:
            btn = QPushButton(action_text)
            btn.setObjectName("primary")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda: action())
            self.body.addWidget(btn, alignment=Qt.AlignmentFlag.AlignHCenter)


class Banner(QFrame):
    """Non-blocking, dismissible notification (success / info / warning / error)."""

    visibilityChanged = Signal(bool)

    _ICON = {"success": ("check", P.SUCCESS), "info": ("about", P.COBALT),
             "warning": ("alert", P.WARNING), "error": ("error", P.ERROR)}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("banner")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(SP_MD, SP_SM, SP_SM, SP_SM)
        lay.setSpacing(SP_MD - 2)
        self._icon = QLabel()
        self._text = QLabel()
        self._text.setObjectName("bannerText")
        self._text.setWordWrap(True)
        self._text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._close = QPushButton()
        self._close.setObjectName("bannerClose")
        self._close.setIcon(icons.icon("close", P.TEXT_MUTED, size=14))
        self._close.setToolTip("Dismiss")
        self._close.setCursor(Qt.CursorShape.PointingHandCursor)
        self._close.clicked.connect(self.dismiss)
        lay.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)
        lay.addWidget(self._text, 1)
        lay.addWidget(self._close, 0, Qt.AlignmentFlag.AlignTop)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self.hide()

    def dismiss(self) -> None:
        self._timer.stop()
        self.hide()
        self.visibilityChanged.emit(False)

    def show_message(self, text: str, kind: str = "info") -> None:
        name, color = self._ICON.get(kind, self._ICON["info"])
        self._icon.setPixmap(icons.pixmap(name, color, 18))
        self._text.setText(text)
        self.setProperty("kind", kind)
        repolish(self)
        self.show()
        self.visibilityChanged.emit(True)
        self._timer.stop()
        if kind in ("success", "info"):
            self._timer.start(6000)  # errors/warnings stay until dismissed


class PageBase(QWidget):
    """Scrollable page with a standard content column."""

    title = "Page"
    subtitle = ""
    scrolls = True

    def __init__(self, main):
        super().__init__()
        self.setObjectName("pageRoot")
        self.main = main
        self._loaded_version = -1
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        inner = QWidget()
        inner.setObjectName("scrollInner")
        self.body = QVBoxLayout(inner)
        self.body.setContentsMargins(SP_XL, SP_XL - 4, SP_XL, SP_XL)
        self.body.setSpacing(SP_LG)
        if self.scrolls:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.viewport().setObjectName("scrollViewport")
            scroll.setWidget(inner)
            outer.addWidget(scroll)
        else:
            outer.addWidget(inner)

    def reload(self) -> None:
        """Refresh content from shared state (must be safe with no data)."""

    def needs_reload(self) -> bool:
        return self._loaded_version != self.main.store.version

    def mark_loaded(self) -> None:
        self._loaded_version = self.main.store.version


class ElidedLabel(QLabel):
    """Single-line label that truncates with an ellipsis instead of forcing
    its container wider (long paths, status messages)."""

    def __init__(self, text: str = "", mode=Qt.TextElideMode.ElideRight, parent=None):
        super().__init__(parent)
        self._mode = mode
        self._full = ""
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(text)

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text
        super().setText(text)
        self.setToolTip(text)
        self.update()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(0, super().minimumSizeHint().height())

    def paintEvent(self, event):  # noqa: N802
        from PySide6.QtGui import QPainter, QPalette
        painter = QPainter(self)
        rect = self.contentsRect()
        text = self.fontMetrics().elidedText(self._full, self._mode, rect.width())
        painter.setPen(self.palette().color(QPalette.ColorRole.WindowText))
        painter.drawText(rect, int(self.alignment()), text)


def soft_path(path) -> str:
    """Let long file paths wrap at separators inside word-wrapped labels."""
    return str(path).replace("/", "/\u200b").replace("\\", "\\\u200b")


def labelled(text: str, widget: QWidget, hint: str = "") -> QWidget:
    """Form field: small caption above its input (and optional helper text)."""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    cap = QLabel(text)
    cap.setObjectName("formLabel")
    cap.setBuddy(widget)
    lay.addWidget(cap)
    lay.addWidget(widget)
    if hint:
        h = QLabel(hint)
        h.setObjectName("cardNote")
        h.setWordWrap(True)
        lay.addWidget(h)
    return box
