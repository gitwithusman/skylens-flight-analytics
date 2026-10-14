"""Flight and Airport Analytics - desktop application (PySide6).

Run from the project root:

    python main_task/gui_main.py

The GUI is a thin presentation layer: all API, validation, processing,
database and analytics work lives in ``src/`` and is shared with the
terminal application.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Optional

# Make ``src`` importable when launched from the project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from PySide6.QtCore import (
    QObject,
    QSortFilterProxyModel,
    Qt,
    QThread,
    Signal,
    QAbstractTableModel,
)
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from src import __version__, analytics, api_client, config, database, service
from src import utils, visualizations
from src.analytics import STATUS_BAR_COLORS

APP_NAME = "Flight and Airport Analytics"

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

QSS = """
* {
    font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: #e8ecf1;
}
QMainWindow, QWidget#central { background: #0e141d; }

/* ---- sidebar ---- */
QFrame#sidebar {
    background: #111a28;
    border-right: 1px solid #1f2b3d;
}
QLabel#brand {
    color: #ffffff;
    font-size: 16px;
    font-weight: 700;
    padding: 18px 16px 4px 16px;
}
QLabel#brandSub {
    color: #7f93ab;
    font-size: 11px;
    padding: 0 16px 14px 16px;
}
QPushButton#nav {
    background: transparent;
    border: none;
    border-radius: 8px;
    color: #aab7c8;
    text-align: left;
    padding: 10px 16px;
    margin: 1px 10px;
    font-weight: 600;
}
QPushButton#nav:hover { background: #1b2940; color: #ffffff; }
QPushButton#nav:checked {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #2b6cb0, stop:1 #3182ce);
    color: #ffffff;
}

/* ---- header ---- */
QFrame#header {
    background: #111a28;
    border-bottom: 1px solid #1f2b3d;
}
QLabel#pageTitle { font-size: 19px; font-weight: 700; color: #ffffff; }
QLabel#pageSubtitle { color: #7f93ab; }

/* ---- cards ---- */
QFrame#card {
    background: #16202f;
    border: 1px solid #223047;
    border-radius: 10px;
}
QLabel#cardTitle { color: #8fa3bd; font-size: 12px; font-weight: 600; }
QLabel#cardValue { color: #ffffff; font-size: 26px; font-weight: 700; }
QLabel#cardNote  { color: #66788f; font-size: 11px; }
QLabel#sectionTitle { color: #ffffff; font-size: 15px; font-weight: 700; }

/* ---- inputs ---- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background: #0e1622;
    border: 1px solid #2a3a52;
    border-radius: 7px;
    padding: 7px 10px;
    selection-background-color: #3182ce;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #4d9de0;
}
QComboBox QAbstractItemView {
    background: #16202f; border: 1px solid #2a3a52;
    selection-background-color: #2b6cb0;
}
QCheckBox { spacing: 6px; }

/* ---- buttons ---- */
QPushButton {
    background: #1c2a3f;
    border: 1px solid #2a3a52;
    border-radius: 7px;
    padding: 8px 16px;
    font-weight: 600;
    color: #d7e1ee;
}
QPushButton:hover { background: #24344d; border-color: #3b5a80; }
QPushButton:pressed { background: #182233; }
QPushButton:disabled { color: #5c6b80; background: #141d2b; }
QPushButton#primary {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #2b6cb0, stop:1 #3182ce);
    border: none;
    color: white;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #3182ce, stop:1 #4299e1);
}
QPushButton#danger { background: #4a2330; border-color: #6e2f42; }
QPushButton#danger:hover { background: #5c2b3d; }

/* ---- tables ---- */
QTableView {
    background: #101825;
    alternate-background-color: #141e2d;
    gridline-color: #1f2b3d;
    border: 1px solid #223047;
    border-radius: 10px;
    selection-background-color: #2b4a73;
    selection-color: #ffffff;
}
QHeaderView::section {
    background: #16202f;
    color: #9fb2c9;
    border: none;
    border-bottom: 1px solid #223047;
    padding: 8px;
    font-weight: 700;
}
QTableCornerButton::section { background: #16202f; }

/* ---- scrollbars ---- */
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical {
    background: #2a3a52; border-radius: 5px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #3b5a80; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; }
QScrollBar::handle:horizontal {
    background: #2a3a52; border-radius: 5px; min-width: 30px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ---- status bar ---- */
QFrame#statusBar {
    background: #111a28;
    border-top: 1px solid #1f2b3d;
}
QLabel#statusChip { font-weight: 600; padding: 4px 10px; border-radius: 9px; }
QLabel#muted { color: #7f93ab; }
QLabel#emptyTitle { color: #ffffff; font-size: 16px; font-weight: 700; }
QLabel#emptyBody { color: #7f93ab; }
"""

ACCENT = "#4d9de0"


# ---------------------------------------------------------------------------
# Threading helpers - keeps the GUI responsive during API / disk work
# ---------------------------------------------------------------------------


class _Worker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fn: Callable, *args, **kwargs):
        super().__init__()
        self._fn, self._args, self._kwargs = fn, args, kwargs

    def run(self):
        try:
            self.finished.emit(self._fn(*self._args, **self._kwargs))
        except Exception as exc:  # surfaced to the GUI as a readable message
            self.failed.emit(str(exc))


def run_in_thread(fn, on_done=None, on_error=None, *args, **kwargs):
    """Execute ``fn`` on a QThread; callbacks fire on the GUI thread."""
    thread = QThread()
    worker = _Worker(fn, *args, **kwargs)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    worker.failed.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    if on_done:
        worker.finished.connect(on_done)
    if on_error:
        worker.failed.connect(on_error)
    thread.start()
    return thread  # caller must keep a reference


# ---------------------------------------------------------------------------
# Reusable widgets
# ---------------------------------------------------------------------------


class StatCard(QFrame):
    """A labelled metric card used on the Dashboard and Analytics pages."""

    def __init__(self, title: str, accent: str = ACCENT, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(4)
        self.title_label = QLabel(title.upper())
        self.title_label.setObjectName("cardTitle")
        self.value_label = QLabel("—")
        self.value_label.setObjectName("cardValue")
        self.value_label.setStyleSheet(f"color: {accent};")
        self.note_label = QLabel("")
        self.note_label.setObjectName("cardNote")
        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)
        layout.addWidget(self.note_label)

    def set_value(self, value, note: str = ""):
        self.value_label.setText(str(value))
        self.note_label.setText(note)


class PandasTableModel(QAbstractTableModel):
    """Simple read-only Qt model wrapping a DataFrame."""

    def __init__(self, df: Optional[pd.DataFrame] = None, parent=None):
        super().__init__(parent)
        self._df = df if df is not None else pd.DataFrame()

    def set_frame(self, df: pd.DataFrame):
        self.beginResetModel()
        self._df = df
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self._df)

    def columnCount(self, parent=None):
        return len(self._df.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            value = self._df.iat[index.row(), index.column()]
            if pd.isna(value):
                return "—"
            if isinstance(value, float) and value == int(value):
                return str(int(value))
            return str(value)
        if role == Qt.ItemDataRole.ForegroundRole:
            col = self._df.columns[index.column()]
            if col == "flight_status":
                status = str(self._df.iat[index.row(), index.column()])
                return QColor(analytics.STATUS_VALUE_COLORS.get(
                    status, "#8a8f98"))
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(self._df.columns[section]).replace("_", " ").title()
        return str(section + 1)


class MultiColumnFilterProxy(QSortFilterProxyModel):
    """Filter that matches the search text against any column."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""

    def set_text(self, text: str):
        self._text = text.lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._text:
            return True
        model = self.sourceModel()
        for col in range(model.columnCount()):
            value = model.index(source_row, col).data()
            if value and self._text in str(value).lower():
                return True
        return False


def make_table(model_holder: list) -> tuple:
    """Create (table_view, proxy) wired to a PandasTableModel."""
    model = PandasTableModel()
    model_holder.append(model)
    proxy = MultiColumnFilterProxy()
    proxy.setSourceModel(model)
    table = QTableView()
    table.setModel(proxy)
    table.setAlternatingRowColors(True)
    table.setSortingEnabled(True)
    table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.Interactive)
    table.horizontalHeader().setStretchLastSection(True)
    table.setWordWrap(False)
    return table, proxy


class EmptyState(QFrame):
    """Shown when no data has been retrieved yet."""

    def __init__(self, on_retrieve: Callable, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(10)
        title = QLabel("No aviation data yet")
        title.setObjectName("emptyTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body = QLabel(
            "Retrieve live flight data from AviationStack to populate the\n"
            "dashboard, tables and charts. Make sure your API key is set\n"
            "in Settings first."
        )
        body.setObjectName("emptyBody")
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        button = QPushButton("Retrieve data now")
        button.setObjectName("primary")
        button.clicked.connect(on_retrieve)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


class PageBase(QWidget):
    """Base page; ``reload`` is called whenever the page becomes visible
    or when fresh data arrives."""

    title = "Page"
    subtitle = ""

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.window = window

    def reload(self):
        """Refresh visible content from shared state (safe when empty)."""


class DashboardPage(PageBase):
    title = "Dashboard"
    subtitle = "Overview of the stored aviation dataset"

    def __init__(self, window):
        super().__init__(window)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(16)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.inner = QWidget()
        self.content = QVBoxLayout(self.inner)
        self.content.setSpacing(16)
        outer.addWidget(self.scroll)
        self.scroll.setWidget(self.inner)

        self.cards_grid = QGridLayout()
        self.cards_grid.setSpacing(14)
        self.card_flights = StatCard("Stored flights", "#4d9de0")
        self.card_airports = StatCard("Airports", "#4caf7d")
        self.card_airlines = StatCard("Airlines", "#c46bd8")
        self.card_delayed = StatCard("Delayed flights", "#e8a33d")
        self.card_routes = StatCard("Routes", "#5bc0de")
        self.card_refresh = StatCard("Last successful refresh", "#9fb2c9")
        for i, card in enumerate([
            self.card_flights, self.card_airports, self.card_airlines,
            self.card_delayed, self.card_routes, self.card_refresh,
        ]):
            self.cards_grid.addWidget(card, i // 3, i % 3)
        self.content.addLayout(self.cards_grid)

        self.empty_state = EmptyState(self.window.start_refresh)
        self.content.addWidget(self.empty_state)

        quick = QFrame()
        quick.setObjectName("card")
        ql = QVBoxLayout(quick)
        ql.setContentsMargins(18, 14, 18, 16)
        head = QLabel("Quick actions")
        head.setObjectName("sectionTitle")
        ql.addWidget(head)
        row = QHBoxLayout()
        for label, target in [
            ("View flights", "flights"),
            ("Browse airports", "airports"),
            ("Search records", "search"),
            ("Open analytics", "analytics"),
            ("Manage data", "data"),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(
                lambda _=False, t=target: self.window.navigate(t))
            row.addWidget(btn)
        row.addStretch(1)
        ql.addLayout(row)
        note = QLabel(
            "Data is retrieved from the AviationStack API, validated with "
            "Pydantic, cleaned with pandas and stored in a local SQLite "
            "database shared with the terminal application."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        ql.addWidget(note)
        self.content.addWidget(quick)
        self.content.addStretch(1)

    def reload(self):
        info = database.database_info()
        has_data = info["flights"] > 0
        self.empty_state.setVisible(not has_data)
        self.card_flights.set_value(utils.format_number(info["flights"]),
                                    "flight records in SQLite")
        self.card_airports.set_value(utils.format_number(info["airports"]),
                                     "airports observed")
        df = database.fetch_flights(limit=100000) if has_data else pd.DataFrame()
        if has_data:
            uniq = analytics.unique_value_counts(df)
            delays = analytics.delay_statistics(df)
            self.card_airlines.set_value(
                utils.format_number(uniq["airlines"]), "distinct carriers")
            self.card_delayed.set_value(
                utils.format_number(delays.get("delayed_flights", 0)),
                f"{delays.get('delayed_share_pct', 0)}% of stored flights"
                if delays.get("available") else "delay data unavailable",
            )
            self.card_routes.set_value(
                utils.format_number(uniq["routes"]), "distinct dep→arr pairs")
            last_ok = info.get("last_success")
            last_any = info.get("last_refresh")
            note = ""
            if info.get("last_refresh_status") and info["last_refresh_status"] != "success":
                note = f"latest attempt: {info['last_refresh_status']}"
            self.card_refresh.set_value(
                last_ok or "never", note or (f"last attempt {last_any}" if last_any else ""))
        else:
            for card in (self.card_airlines, self.card_delayed,
                         self.card_routes):
                card.set_value("—", "no data")
            self.card_refresh.set_value("never")


class FlightsPage(PageBase):
    title = "Flights"
    subtitle = "Stored flight records from AviationStack"

    def __init__(self, window):
        super().__init__(window)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search flights, airlines, airports…")
        self.search.textChanged.connect(self._filter)
        self.status = QComboBox()
        self.status.addItem("All statuses", "")
        for s in api_client.FILTERABLE_STATUSES:
            self.status.addItem(s.title(), s)
        self.status.currentIndexChanged.connect(self._filter)
        self.delayed = QCheckBox("Delayed only")
        self.delayed.stateChanged.connect(self._filter)
        self.count_label = QLabel("")
        self.count_label.setObjectName("muted")
        refresh = QPushButton("Reload")
        refresh.clicked.connect(self.reload)
        bar.addWidget(self.search, 3)
        bar.addWidget(self.status)
        bar.addWidget(self.delayed)
        bar.addWidget(self.count_label)
        bar.addWidget(refresh)
        layout.addLayout(bar)

        self._models = []
        self.table, self.proxy = make_table(self._models)
        layout.addWidget(self.table)
        self.df = pd.DataFrame()

    def reload(self):
        self.df = database.fetch_flights()
        self._apply()
        self.window.refresh_status_bar()

    def _filter(self):
        self._apply()

    def _apply(self):
        df = self.df
        status = self.status.currentData()
        if status:
            df = df[df["flight_status"] == status]
        if self.delayed.isChecked() and "max_delay_min" in df:
            df = df[df["max_delay_min"].fillna(0) > 0]
        self.proxy.set_text(self.search.text())
        self._models[0].set_frame(df)
        total = len(self.df)
        self.count_label.setText(f"{len(df)} of {total} records")


class AirportsPage(PageBase):
    title = "Airports"
    subtitle = "Airports observed in stored flight records"

    def __init__(self, window):
        super().__init__(window)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search airport name or IATA code…")
        self.count_label = QLabel("")
        self.count_label.setObjectName("muted")
        refresh = QPushButton("Reload")
        refresh.clicked.connect(self.reload)
        bar.addWidget(self.search, 3)
        bar.addWidget(self.count_label)
        bar.addWidget(refresh)
        layout.addLayout(bar)

        self._models = []
        self.table, self.proxy = make_table(self._models)
        self.search.textChanged.connect(self.proxy.set_text)
        layout.addWidget(self.table)

        note = QLabel(
            "Airport records are derived from the departure and arrival "
            "details inside each stored flight - the free AviationStack "
            "plan does not expose a separate airports directory."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        layout.addWidget(note)

    def reload(self):
        df = database.fetch_airports()
        self._models[0].set_frame(df)
        self.count_label.setText(f"{len(df)} airports")


class SearchPage(PageBase):
    title = "Search"
    subtitle = "Find stored records by field, status and route"

    def __init__(self, window):
        super().__init__(window)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        form = QFrame()
        form.setObjectName("card")
        grid = QGridLayout(form)
        grid.setContentsMargins(18, 16, 18, 16)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)

        self.term = QLineEdit()
        self.term.setPlaceholderText("Text to match…")
        self.field = QComboBox()
        self.field.addItem("All common fields", None)
        for col in ("flight_iata", "flight_number", "airline_name",
                    "dep_airport", "dep_iata", "arr_airport", "arr_iata",
                    "route", "flight_status"):
            self.field.addItem(col.replace("_", " ").title(), col)
        self.status = QComboBox()
        self.status.addItem("Any status", "")
        for s in api_client.FILTERABLE_STATUSES:
            self.status.addItem(s.title(), s)
        self.dep = QLineEdit()
        self.dep.setPlaceholderText("Departure IATA (e.g. JFK)")
        self.arr = QLineEdit()
        self.arr.setPlaceholderText("Arrival IATA (e.g. LHR)")
        self.delayed = QCheckBox("Delayed only")

        run = QPushButton("Search")
        run.setObjectName("primary")
        run.clicked.connect(self._run)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear)

        grid.addWidget(QLabel("Search text"), 0, 0)
        grid.addWidget(self.term, 0, 1)
        grid.addWidget(QLabel("Search field"), 0, 2)
        grid.addWidget(self.field, 0, 3)
        grid.addWidget(QLabel("Status"), 1, 0)
        grid.addWidget(self.status, 1, 1)
        grid.addWidget(QLabel("From"), 1, 2)
        grid.addWidget(self.dep, 1, 3)
        grid.addWidget(QLabel("To"), 2, 0)
        grid.addWidget(self.arr, 2, 1)
        grid.addWidget(self.delayed, 2, 2)
        row = QHBoxLayout()
        row.addWidget(run)
        row.addWidget(clear)
        row.addStretch(1)
        grid.addLayout(row, 2, 3)
        layout.addWidget(form)

        self.result_label = QLabel("Enter criteria and press Search.")
        self.result_label.setObjectName("muted")
        layout.addWidget(self.result_label)

        self._models = []
        self.table, self.proxy = make_table(self._models)
        layout.addWidget(self.table)

    def _run(self):
        term = self.term.text().strip()
        field = self.field.currentData()
        if not any([
            term,
            self.status.currentData(),
            self.dep.text().strip(),
            self.arr.text().strip(),
            self.delayed.isChecked(),
        ]):
            self.result_label.setText(
                "Enter at least one criterion before searching.")
            return

        kwargs = {}
        if term:
            kwargs["search"] = term
            if field:
                kwargs["search_fields"] = [field]
        if self.status.currentData():
            kwargs["status"] = self.status.currentData()
        if self.dep.text().strip():
            kwargs["dep_iata"] = self.dep.text().strip()
        if self.arr.text().strip():
            kwargs["arr_iata"] = self.arr.text().strip()
        kwargs["delayed_only"] = self.delayed.isChecked()

        df = database.fetch_flights(**kwargs)
        self._models[0].set_frame(df)
        total = database.count_rows("flights")
        self.result_label.setText(
            f"{len(df)} matching record(s) out of {total} stored.")

    def _clear(self):
        for widget in (self.term, self.dep, self.arr):
            widget.clear()
        self.field.setCurrentIndex(0)
        self.status.setCurrentIndex(0)
        self.delayed.setChecked(False)
        self._models[0].set_frame(pd.DataFrame())
        self.result_label.setText("Filters cleared.")

    def reload(self):
        pass  # results are user-driven; nothing to preload


class AnalyticsPage(PageBase):
    title = "Analytics"
    subtitle = "Statistics calculated from the stored dataset"

    def __init__(self, window):
        super().__init__(window)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        inner = QWidget()
        self.layout = QVBoxLayout(inner)
        self.layout.setContentsMargins(24, 20, 24, 20)
        self.layout.setSpacing(14)
        scroll.setWidget(inner)

        self.cards = QGridLayout()
        self.cards.setSpacing(14)
        self.card_specs = [
            ("Flights", "#4d9de0"), ("Airlines", "#c46bd8"),
            ("Departure airports", "#4caf7d"), ("Arrival airports", "#4caf7d"),
            ("Routes", "#5bc0de"), ("Avg delay", "#e8a33d"),
            ("Delayed share", "#e8a33d"), ("Codeshared", "#f0ad4e"),
        ]
        self._cards = []
        for i, (label, color) in enumerate(self.card_specs):
            card = StatCard(label, color)
            self._cards.append(card)
            self.cards.addWidget(card, i // 4, i % 4)
        self.layout.addLayout(self.cards)

        self.tables_frame = QFrame()
        tfl = QGridLayout(self.tables_frame)
        tfl.setSpacing(14)
        self._tables = {}
        specs = [
            ("status", "Flight status distribution", 0, 0),
            ("airlines", "Top airlines", 0, 1),
            ("dep", "Top departure airports", 1, 0),
            ("arr", "Top arrival airports", 1, 1),
            ("routes", "Top routes", 2, 0),
            ("hours", "Departures by hour (UTC)", 2, 1),
        ]
        for key, title, r, c in specs:
            card = QFrame()
            card.setObjectName("card")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 12, 14, 12)
            head = QLabel(title)
            head.setObjectName("sectionTitle")
            cl.addWidget(head)
            models = []
            table, _ = make_table(models)
            table.setMinimumHeight(210)
            cl.addWidget(table)
            self._tables[key] = models
            tfl.addWidget(card, r, c)
        self.layout.addWidget(self.tables_frame)
        self.layout.addStretch(1)

    def reload(self):
        df = database.fetch_flights()
        uniq = analytics.unique_value_counts(df)
        delays = analytics.delay_statistics(df)
        cs = analytics.codeshare_share(df)
        values = [
            utils.format_number(len(df)),
            utils.format_number(uniq["airlines"]),
            utils.format_number(uniq["departure_airports"]),
            utils.format_number(uniq["arrival_airports"]),
            utils.format_number(uniq["routes"]),
            f"{delays['avg_delay_min']} min" if delays.get("available") else "n/a",
            f"{delays['delayed_share_pct']}%" if delays.get("available") else "n/a",
            f"{cs['codeshared']} ({cs['share_pct']}%)",
        ]
        notes = ["stored records", "distinct carriers", "distinct airports",
                 "distinct airports", "dep→arr pairs",
                 delays.get("reason", ""), "of stored flights", "of flights"]
        for card, value, note in zip(self._cards, values, notes):
            card.set_value(value, note)

        tables = {
            "status": analytics.status_distribution(df),
            "airlines": analytics.top_airlines(df),
            "dep": analytics.top_airports(df, "dep"),
            "arr": analytics.top_airports(df, "arr"),
            "routes": analytics.top_routes(df),
            "hours": analytics.departure_hour_distribution(df),
        }
        for key, frame in tables.items():
            self._tables[key][0].set_frame(frame)


class VisualizationsPage(PageBase):
    title = "Visualizations"
    subtitle = "Charts generated from the stored dataset"

    def __init__(self, window):
        super().__init__(window)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        bar = QHBoxLayout()
        self.selector = QComboBox()
        for key, meta in visualizations.CHART_TYPES.items():
            self.selector.addItem(meta["title"], key)
        self.selector.currentIndexChanged.connect(self._render)
        refresh = QPushButton("Regenerate")
        refresh.clicked.connect(self._render)
        save = QPushButton("Save PNG…")
        save.clicked.connect(self._save)
        bar.addWidget(QLabel("Chart:"))
        bar.addWidget(self.selector, 2)
        bar.addWidget(refresh)
        bar.addWidget(save)
        bar.addStretch(1)
        layout.addLayout(bar)

        self.canvas = FigureCanvasQTAgg(Figure(figsize=(8, 5)))
        self.canvas.setStyleSheet("background: transparent;")
        layout.addWidget(self.canvas)
        self._figure = None

    def _render(self):
        df = database.fetch_flights()
        key = self.selector.currentData()
        if self._figure is not None:
            self._figure.clear()
        self._figure = visualizations.build_chart(key, df)
        # replace canvas figure
        layout = self.canvas.parentWidget().layout()
        layout.removeWidget(self.canvas)
        self.canvas.deleteLater()
        self.canvas = FigureCanvasQTAgg(self._figure)
        self.canvas.setStyleSheet("background: transparent;")
        layout.addWidget(self.canvas)
        self.canvas.draw_idle()

    def _save(self):
        if self._figure is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save chart", str(config.VISUALIZATIONS_DIR / "chart.png"),
            "PNG image (*.png)")
        if path:
            try:
                self._figure.savefig(path, dpi=130, bbox_inches="tight")
                self.window.notify(f"Chart saved to {path}")
            except Exception as exc:
                self.window.notify(f"Could not save chart: {exc}", error=True)

    def reload(self):
        self._render()


class DataPage(PageBase):
    title = "Data Management"
    subtitle = "Retrieve, inspect and export aviation data"

    def __init__(self, window):
        super().__init__(window)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)
        scroll.setWidget(inner)

        # --- retrieval card -------------------------------------------------
        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 16, 18, 16)
        cl.setSpacing(10)
        head = QLabel("Retrieve data from AviationStack")
        head.setObjectName("sectionTitle")
        cl.addWidget(head)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        self.limit = QSpinBox()
        self.limit.setRange(1, config.MAX_RECORD_LIMIT)
        self.limit.setValue(config.DEFAULT_RECORD_LIMIT)
        self.f_status = QComboBox()
        self.f_status.addItem("Any status", "")
        for s in api_client.FILTERABLE_STATUSES:
            self.f_status.addItem(s.title(), s)
        self.f_dep = QLineEdit()
        self.f_dep.setPlaceholderText("Departure IATA")
        self.f_arr = QLineEdit()
        self.f_arr.setPlaceholderText("Arrival IATA")
        self.f_airline = QLineEdit()
        self.f_airline.setPlaceholderText("Airline name")
        self.f_number = QLineEdit()
        self.f_number.setPlaceholderText("Flight number")
        grid.addWidget(QLabel("Records"), 0, 0)
        grid.addWidget(self.limit, 0, 1)
        grid.addWidget(QLabel("Status"), 0, 2)
        grid.addWidget(self.f_status, 0, 3)
        grid.addWidget(QLabel("From"), 1, 0)
        grid.addWidget(self.f_dep, 1, 1)
        grid.addWidget(QLabel("To"), 1, 2)
        grid.addWidget(self.f_arr, 1, 3)
        grid.addWidget(QLabel("Airline"), 2, 0)
        grid.addWidget(self.f_airline, 2, 1)
        grid.addWidget(QLabel("Flight no."), 2, 2)
        grid.addWidget(self.f_number, 2, 3)
        cl.addLayout(grid)

        self.retrieve_btn = QPushButton("Retrieve flights")
        self.retrieve_btn.setObjectName("primary")
        self.retrieve_btn.clicked.connect(self._retrieve)
        cl.addWidget(self.retrieve_btn)
        self.retrieve_status = QLabel("")
        self.retrieve_status.setObjectName("muted")
        self.retrieve_status.setWordWrap(True)
        cl.addWidget(self.retrieve_status)
        layout.addWidget(card)

        # --- database card --------------------------------------------------
        db_card = QFrame()
        db_card.setObjectName("card")
        dl = QVBoxLayout(db_card)
        dl.setContentsMargins(18, 16, 18, 16)
        dl.setSpacing(6)
        head = QLabel("Local database")
        head.setObjectName("sectionTitle")
        dl.addWidget(head)
        self.db_info_label = QLabel("")
        self.db_info_label.setObjectName("muted")
        dl.addWidget(self.db_info_label)
        layout.addWidget(db_card)

        # --- export card ----------------------------------------------------
        ex = QFrame()
        ex.setObjectName("card")
        el = QVBoxLayout(ex)
        el.setContentsMargins(18, 16, 18, 16)
        el.setSpacing(10)
        head = QLabel("Export")
        head.setObjectName("sectionTitle")
        el.addWidget(head)
        row = QHBoxLayout()
        for label, table, fmt in [
            ("Flights → CSV", "flights", "csv"),
            ("Flights → JSON", "flights", "json"),
            ("Airports → CSV", "airports", "csv"),
            ("Airports → JSON", "airports", "json"),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(
                lambda _=False, t=table, f=fmt: self._export(t, f))
            row.addWidget(btn)
        summary_btn = QPushButton("Analytics summary → JSON")
        summary_btn.clicked.connect(self._export_summary)
        row.addWidget(summary_btn)
        row.addStretch(1)
        el.addLayout(row)
        layout.addWidget(ex)
        layout.addStretch(1)

    def _retrieve(self):
        self.window.start_refresh(
            limit=self.limit.value(),
            flight_status=self.f_status.currentData() or None,
            dep_iata=self.f_dep.text().strip() or None,
            arr_iata=self.f_arr.text().strip() or None,
            airline_name=self.f_airline.text().strip() or None,
            flight_number=self.f_number.text().strip() or None,
        )

    def _export(self, table, fmt):
        if database.count_rows(table) == 0:
            self.window.notify(
                f"The '{table}' table is empty - retrieve data first.",
                error=True)
            return
        try:
            path = database.export_table(table, fmt)
            self.window.notify(f"Exported {table} → {path}")
        except Exception as exc:
            self.window.notify(f"Export failed: {exc}", error=True)

    def _export_summary(self):
        df = database.fetch_flights()
        if df.empty:
            self.window.notify("No data to summarise yet.", error=True)
            return
        try:
            summary = analytics.full_summary(df, database.fetch_airports())
            path = database.export_summary_json(summary, "analytics_summary")
            self.window.notify(f"Summary exported → {path}")
        except Exception as exc:
            self.window.notify(f"Export failed: {exc}", error=True)

    def set_busy(self, busy: bool):
        self.retrieve_btn.setEnabled(not busy)
        self.retrieve_status.setText(
            "Contacting AviationStack… this can take a few seconds."
            if busy else "")

    def set_result(self, result: service.RefreshResult):
        errors = ""
        if result.validation_errors:
            preview = "\n".join(result.validation_errors[:3])
            errors = f"\nValidation issues:\n{preview}"
        self.retrieve_status.setText(
            f"{result.message}\n"
            f"fetched {result.fetched} • valid {result.valid} • "
            f"stored {result.stored} • airports {result.airports_stored}"
            + errors)

    def set_error(self, message: str):
        self.retrieve_status.setText(f"Refresh failed: {message}")

    def reload(self):
        info = database.database_info()
        last = database.last_refresh()
        lines = [
            f"Database file : {info['path']}",
            f"Size          : {info['size_kb']} KB",
            f"Flights       : {utils.format_number(info['flights'])}",
            f"Airports      : {utils.format_number(info['airports'])}",
            f"Last refresh  : {utils.safe_str(info['last_refresh'])}",
            f"Last success  : {utils.safe_str(info['last_success'])}",
        ]
        if last and last.get("status") != "success":
            lines.append(
                f"Latest attempt: {last['status']} - {last.get('message','')}")
        self.db_info_label.setText("\n".join(lines))


class SettingsPage(PageBase):
    title = "Settings"
    subtitle = "Data source and application options"

    def __init__(self, window):
        super().__init__(window)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        form.setContentsMargins(18, 16, 18, 16)
        form.setSpacing(12)

        head = QLabel("AviationStack API")
        head.setObjectName("sectionTitle")
        form.addRow(head)
        self.key_status = QLabel()
        self.key_status.setObjectName("muted")
        self.key_status.setWordWrap(True)
        form.addRow("Configured key:", self.key_status)

        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("Paste new API key (leave blank to keep)")
        form.addRow("New API key:", self.key_input)

        note = QLabel(
            "The key is stored in the .env file at the project root and is "
            "never shown in full. Get a free key at aviationstack.com."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        form.addRow(note)
        layout.addWidget(card)

        weather_card = QFrame()
        weather_card.setObjectName("card")
        wform = QFormLayout(weather_card)
        wform.setContentsMargins(18, 16, 18, 16)
        wform.setSpacing(12)
        whead = QLabel("Weather lookup (Open-Meteo, optional)")
        whead.setObjectName("sectionTitle")
        wform.addRow(whead)
        self.weather_enabled = QCheckBox("Enable weather status in the status bar")
        wform.addRow(self.weather_enabled)
        self.weather_label = QLineEdit()
        self.weather_label.setPlaceholderText("Display name, e.g. 'Home airport'")
        wform.addRow("Location label:", self.weather_label)
        self.weather_lat = QDoubleSpinBox()
        self.weather_lat.setRange(-90, 90)
        self.weather_lat.setDecimals(4)
        self.weather_lon = QDoubleSpinBox()
        self.weather_lon.setRange(-180, 180)
        self.weather_lon.setDecimals(4)
        wform.addRow("Latitude:", self.weather_lat)
        wform.addRow("Longitude:", self.weather_lon)
        wnote = QLabel(
            "Weather is shown for context only; delays are attributed to "
            "weather only when the flight data source confirms it."
        )
        wnote.setObjectName("muted")
        wnote.setWordWrap(True)
        wform.addRow(wnote)
        layout.addWidget(weather_card)

        row = QHBoxLayout()
        save = QPushButton("Save settings")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        row.addWidget(save)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addStretch(1)

    def _save(self):
        values = {}
        new_key = self.key_input.text().strip()
        if new_key:
            values["AVIATIONSTACK_API_KEY"] = new_key
        values["ENABLE_WEATHER_LOOKUP"] = (
            "1" if self.weather_enabled.isChecked() else "0")
        if self.weather_label.text().strip():
            values["WEATHER_LABEL"] = self.weather_label.text().strip()
        if self.weather_lat.value() != 0:
            values["WEATHER_LATITUDE"] = f"{self.weather_lat.value():.4f}"
        if self.weather_lon.value() != 0:
            values["WEATHER_LONGITUDE"] = f"{self.weather_lon.value():.4f}"
        try:
            config.update_env_file(values)
            config.reload_environment()
            self.key_input.clear()
            self.reload()
            self.window.refresh_status_bar()
            self.window.notify("Settings saved.")
        except Exception as exc:
            self.window.notify(f"Could not save settings: {exc}", error=True)

    def reload(self):
        self.key_status.setText(
            config.masked_api_key()
            if config.api_key_configured()
            else "Not configured - data retrieval is unavailable")
        self.weather_enabled.setChecked(config.ENABLE_WEATHER_LOOKUP)
        self.weather_label.setText(config.WEATHER_LABEL)
        try:
            self.weather_lat.setValue(float(config.WEATHER_LATITUDE or 0))
            self.weather_lon.setValue(float(config.WEATHER_LONGITUDE or 0))
        except ValueError:
            pass


class AboutPage(PageBase):
    title = "About"
    subtitle = "Application information"

    def __init__(self, window):
        super().__init__(window)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(28, 24, 28, 24)
        cl.setSpacing(8)
        name = QLabel(f"{APP_NAME} v{__version__}")
        name.setStyleSheet("font-size: 22px; font-weight: 800; color: #ffffff;")
        desc = QLabel(
            "A desktop and terminal application for retrieving, exploring "
            "and analysing flight and airport information.\n\n"
            "Pipeline: AviationStack REST API → Pydantic validation → "
            "pandas processing → SQLite storage → analytics and charts.\n\n"
            "Weather context: Open-Meteo (optional).\n"
            "Built with Python, PySide6, pandas, Pydantic, Matplotlib "
            "and SQLite."
        )
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        cl.addWidget(name)
        cl.addWidget(desc)
        layout.addWidget(card)
        layout.addStretch(1)


# ---------------------------------------------------------------------------
# Status bar with flight-condition chips
# ---------------------------------------------------------------------------


class FlightStatusBar(QFrame):
    """Bottom strip summarising live conditions of stored flights."""

    CATEGORIES = ["On Time", "Delayed", "Cancelled", "Weather Alert",
                  "Weather Delay", "Landed", "Status Unknown"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusBar")
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(14, 6, 14, 6)
        self.layout.setSpacing(8)
        lead = QLabel("Flight conditions:")
        lead.setObjectName("muted")
        self.layout.addWidget(lead)
        self._chips = {}
        for cat in self.CATEGORIES:
            chip = QLabel(f"● {cat}: 0")
            chip.setObjectName("statusChip")
            color = STATUS_BAR_COLORS[cat]
            chip.setStyleSheet(
                f"color: {color}; background: {color}22; border-radius: 9px;")
            chip.setVisible(False)
            self._chips[cat] = chip
            self.layout.addWidget(chip)
        self.weather_chip = QLabel("")
        self.weather_chip.setObjectName("statusChip")
        self.weather_chip.setStyleSheet(
            "color: #9fd0ff; background: #2b6cb033; border-radius: 9px;")
        self.weather_chip.setVisible(False)
        self.layout.addWidget(self.weather_chip)
        self.layout.addStretch(1)
        self.message = QLabel("Ready")
        self.message.setObjectName("muted")
        self.layout.addWidget(self.message)

    def update_conditions(self, df: pd.DataFrame):
        counts = {cat: 0 for cat in self.CATEGORIES}
        if not df.empty:
            for _, row in df.iterrows():
                cond = analytics.classify_condition(row)
                label = cond["label"]
                base = next((c for c in self.CATEGORIES
                             if label.startswith(c)), "Status Unknown")
                counts[base] += 1
        has_data = not df.empty
        for cat, chip in self._chips.items():
            chip.setText(f"● {cat}: {counts[cat]}")
            # When data exists, always show the three headline categories so
            # the bar is stable; optional ones only appear when non-zero.
            always = cat in ("On Time", "Delayed", "Cancelled")
            chip.setVisible(has_data and (always or counts[cat] > 0))

    def set_weather(self, text: Optional[str]):
        self.weather_chip.setText(text or "")
        self.weather_chip.setVisible(bool(text))

    def set_message(self, text: str):
        self.message.setText(text)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    NAV = [
        ("dashboard", "⌂", "Dashboard"),
        ("flights", "✈", "Flights"),
        ("airports", "▣", "Airports"),
        ("search", "⌕", "Search"),
        ("analytics", "∑", "Analytics"),
        ("charts", "◔", "Visualizations"),
        ("data", "⛁", "Data"),
        ("settings", "⚙", "Settings"),
        ("about", "ⓘ", "About"),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)
        self.setMinimumSize(1024, 640)
        self._threads = []

        central = QWidget()
        central.setObjectName("central")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        # ---- sidebar -------------------------------------------------------
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(210)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(0, 0, 0, 12)
        sb.setSpacing(0)
        brand = QLabel("✈ " + APP_NAME.split(" and ")[0])
        brand.setObjectName("brand")
        brand_sub = QLabel("Flight & Airport Analytics")
        brand_sub.setObjectName("brandSub")
        sb.addWidget(brand)
        sb.addWidget(brand_sub)
        self.nav_buttons = {}
        for key, icon, label in self.NAV:
            btn = QPushButton(f"  {icon}   {label}")
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, k=key: self.navigate(k))
            self.nav_buttons[key] = btn
            sb.addWidget(btn)
        sb.addStretch(1)
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("brandSub")
        sb.addWidget(ver)
        root.addWidget(sidebar)

        # ---- main column ----------------------------------------------------
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        root.addLayout(column)

        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(64)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 0, 24, 0)
        titles = QVBoxLayout()
        self.page_title = QLabel("Dashboard")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel("")
        self.page_subtitle.setObjectName("pageSubtitle")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_subtitle)
        hl.addLayout(titles)
        hl.addStretch(1)
        self.refresh_btn = QPushButton("↻ Refresh data")
        self.refresh_btn.setObjectName("primary")
        self.refresh_btn.clicked.connect(lambda: self.start_refresh())
        hl.addWidget(self.refresh_btn)
        column.addWidget(header)

        # ---- pages -----------------------------------------------------------
        self.stack = QStackedWidget()
        column.addWidget(self.stack)
        self.pages = {
            "dashboard": DashboardPage(self),
            "flights": FlightsPage(self),
            "airports": AirportsPage(self),
            "search": SearchPage(self),
            "analytics": AnalyticsPage(self),
            "charts": VisualizationsPage(self),
            "data": DataPage(self),
            "settings": SettingsPage(self),
            "about": AboutPage(self),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)

        # ---- status bar -------------------------------------------------------
        self.status_bar = FlightStatusBar()
        column.addWidget(self.status_bar)

        self.navigate("dashboard")
        self.refresh_status_bar()

    # -- navigation ---------------------------------------------------------

    def navigate(self, key: str):
        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == key)
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        self.page_title.setText(page.title)
        self.page_subtitle.setText(page.subtitle)
        try:
            page.reload()
        except Exception as exc:
            self.notify(f"Could not load page: {exc}", error=True)

    # -- async refresh --------------------------------------------------------

    def _spawn(self, fn, on_done=None, on_error=None, **kwargs):
        """Run ``fn`` on a worker thread and drop the reference when done."""
        thread = run_in_thread(fn, on_done, on_error, **kwargs)
        self._threads.append(thread)
        thread.finished.connect(
            lambda t=thread: self._threads.remove(t)
            if t in self._threads else None)
        return thread

    def start_refresh(self, **filters):
        if not config.api_key_configured():
            self.notify(
                "No API key configured - open Settings to add one.",
                error=True)
            self.navigate("settings")
            return
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("Retrieving…")
        data_page: DataPage = self.pages["data"]
        data_page.set_busy(True)
        self.status_bar.set_message("Retrieving flights from AviationStack…")

        self._spawn(
            service.refresh_data,
            lambda result: self._refresh_done(result),
            self._refresh_failed,
            **filters,
        )

    def _refresh_done(self, result: service.RefreshResult):
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("↻ Refresh data")
        data_page: DataPage = self.pages["data"]
        data_page.set_busy(False)
        data_page.set_result(result)
        self.status_bar.set_message(result.message)
        self.notify(result.message)
        self.refresh_status_bar()
        try:
            self.pages[self._current_key()].reload()
        except Exception:
            pass

    def _refresh_failed(self, message: str):
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("↻ Refresh data")
        data_page: DataPage = self.pages["data"]
        data_page.set_busy(False)
        data_page.set_error(message)
        self.status_bar.set_message("Refresh failed")
        self.notify(f"Refresh failed: {message}", error=True)

    def _current_key(self) -> str:
        widget = self.stack.currentWidget()
        for k, p in self.pages.items():
            if p is widget:
                return k
        return "dashboard"

    # -- status bar -------------------------------------------------------------

    def refresh_status_bar(self):
        try:
            df = database.fetch_flights()
            self.status_bar.update_conditions(df)
        except Exception:
            self.status_bar.update_conditions(pd.DataFrame())

        # Optional weather context for a configured location
        if (config.ENABLE_WEATHER_LOOKUP and config.WEATHER_LATITUDE
                and config.WEATHER_LONGITUDE):
            try:
                lat = float(config.WEATHER_LATITUDE)
                lon = float(config.WEATHER_LONGITUDE)
            except ValueError:
                lat = lon = None
            if lat is not None:
                def _wx():
                    return api_client.fetch_weather(lat, lon)

                def _done(weather):
                    if weather:
                        text = (f"☁ {config.WEATHER_LABEL}: "
                                f"{api_client.weather_summary(weather)}")
                        self.status_bar.set_weather(text)

                self._spawn(_wx, _done, lambda _e: None)
        else:
            self.status_bar.set_weather(None)

    def notify(self, message: str, error: bool = False):
        self.status_bar.set_message(message)
        if error:
            QMessageBox.warning(self, APP_NAME, message)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(QSS)
    icon_path = config.ASSETS_DIR / "icons" / "app.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
