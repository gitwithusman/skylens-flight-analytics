"""Table model, proxy and view used by every data grid in the GUI."""

from __future__ import annotations

from typing import Dict, Iterable, Optional

import pandas as pd
from PySide6.QtCore import (
    QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractItemView, QHeaderView, QLabel, QTableView,
)

from src import analytics

HEADER_LABELS: Dict[str, str] = {
    "flight_date": "Date", "flight_iata": "Flight", "flight_icao": "ICAO flight",
    "flight_number": "No.", "flight_status": "Status", "airline_name": "Airline",
    "airline_iata": "Airline code", "airline_icao": "Airline ICAO",
    "dep_airport": "Departure airport", "dep_iata": "From", "dep_icao": "From ICAO",
    "dep_scheduled": "Departs (UTC)", "dep_estimated": "Est. departure",
    "dep_actual": "Actual departure", "dep_delay_min": "Dep. delay (min)",
    "dep_terminal": "Dep. terminal", "dep_gate": "Dep. gate",
    "arr_airport": "Arrival airport", "arr_iata": "To", "arr_icao": "To ICAO",
    "arr_scheduled": "Arrives (UTC)", "arr_estimated": "Est. arrival",
    "arr_actual": "Actual arrival", "arr_delay_min": "Arr. delay (min)",
    "max_delay_min": "Max delay (min)", "route": "Route",
    "is_codeshared": "Codeshare", "airport_name": "Airport", "iata": "IATA",
    "icao": "ICAO", "timezone": "Time zone", "departures": "Departures",
    "arrivals": "Arrivals", "sightings": "Total",
}

_TS_COLUMNS_HINT = ("scheduled", "estimated", "actual", "retrieved_at")


def format_cell(column: str, value) -> str:
    """Display text for one cell (blank values show as an en dash)."""
    if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
        return "\u2013"
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, bool) or str(type(value)).endswith("bool_'>"):
        return "Yes" if value else "No"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.1f}"
    text = str(value)
    if column == "flight_status":
        return text.replace("_", " ").capitalize()
    if any(h in column for h in _TS_COLUMNS_HINT) and "T" in text[:11]:
        return text[:16].replace("T", " ")
    return text


class PandasTableModel(QAbstractTableModel):
    """Read-only model over a DataFrame with proper numeric sorting."""

    SORT_ROLE = Qt.ItemDataRole.UserRole

    def __init__(self, parent=None):
        super().__init__(parent)
        self._df = pd.DataFrame()
        self._display: list = []

    def set_frame(self, df: pd.DataFrame) -> None:
        self.beginResetModel()
        self._df = df.reset_index(drop=True)
        cols = list(self._df.columns)
        self._display = [
            [format_cell(c, v) for c, v in zip(cols, row)]
            for row in self._df.itertuples(index=False, name=None)
        ]
        self.endResetModel()

    def frame(self) -> pd.DataFrame:
        return self._df

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._df.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            return self._display[row][col]
        if role == self.SORT_ROLE:
            value = self._df.iat[row, col]
            if value is None or (not isinstance(value, (list, dict)) and pd.isna(value)):
                return None
            if isinstance(value, pd.Timestamp):
                return value.isoformat()
            if isinstance(value, (bool, int, float)):
                return float(value)
            if hasattr(value, "item"):
                return value.item()
            return str(value).lower()
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if pd.api.types.is_numeric_dtype(self._df.dtypes.iloc[col]) and \
                    not pd.api.types.is_bool_dtype(self._df.dtypes.iloc[col]):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole:
            if self._df.columns[col] == "flight_status":
                status = str(self._df.iat[row, col]).lower()
                color = analytics.STATUS_VALUE_COLORS.get(status)
                return QColor(color) if color else None
        if role == Qt.ItemDataRole.FontRole:
            if self._df.columns[col] == "flight_status":
                font = QFont()
                font.setBold(True)
                return font
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._display[row][col]
        return None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                name = str(self._df.columns[section])
                return HEADER_LABELS.get(name, name.replace("_", " ").capitalize())
            return str(section + 1)
        return None


class SortProxy(QSortFilterProxyModel):
    """Sorts on the raw values (numbers numerically, blanks last)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(PandasTableModel.SORT_ROLE)

    def lessThan(self, left, right):  # noqa: N802 - Qt naming
        a = self.sourceModel().data(left, PandasTableModel.SORT_ROLE)
        b = self.sourceModel().data(right, PandasTableModel.SORT_ROLE)
        if a is None or b is None:
            if a is None and b is None:
                return False
            # keep blanks at the bottom for both sort directions
            asc = self.sortOrder() == Qt.SortOrder.AscendingOrder
            return (b is None) if asc else (a is None)
        try:
            return a < b
        except TypeError:
            return str(a) < str(b)


class DataTable(QTableView):
    """Styled, sortable grid with an empty-state message."""

    MIN_COL, MAX_COL, SAMPLE_ROWS = 72, 300, 200

    def __init__(self, empty_text: str = "No records to display.", parent=None):
        super().__init__(parent)
        self.table_model = PandasTableModel(self)
        self._proxy = SortProxy(self)
        self._proxy.setSourceModel(self.table_model)
        self.setModel(self._proxy)
        self.setAlternatingRowColors(True)
        self.setSortingEnabled(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(32)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(True)
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        header.setMinimumSectionSize(self.MIN_COL)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._empty = QLabel(empty_text, self.viewport())
        self._empty.setObjectName("muted")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setWordWrap(True)

    def set_empty_text(self, text: str) -> None:
        self._empty.setText(text)

    def set_frame(self, df: pd.DataFrame, columns: Optional[Iterable[str]] = None) -> None:
        if columns is not None:
            cols = [c for c in columns if c in df.columns]
            df = df[cols] if cols else df
        self.table_model.set_frame(df)
        self._fit_columns()
        self._empty.setVisible(df.empty)
        self._place_empty()

    def _fit_columns(self) -> None:
        fm = QFontMetrics(self.font())
        header_fm = QFontMetrics(self.horizontalHeader().font())
        df = self.table_model.frame()
        sample = self.table_model._display[: self.SAMPLE_ROWS]
        for col in range(len(df.columns)):
            title = self.table_model.headerData(col, Qt.Orientation.Horizontal)
            width = header_fm.horizontalAdvance(str(title)) + 44  # sort arrow room
            extra = 14 if df.columns[col] == "flight_status" else 0  # bold text
            for row in sample:
                width = max(width, fm.horizontalAdvance(row[col]) + 24 + extra)
            self.setColumnWidth(col, max(self.MIN_COL, min(self.MAX_COL, width)))

    def _place_empty(self) -> None:
        vp = self.viewport()
        self._empty.setGeometry(24, 40, max(0, vp.width() - 48), max(0, vp.height() - 80))

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._place_empty()


def search_haystack(df: pd.DataFrame, columns: Iterable[str]) -> pd.Series:
    """One lower-case searchable string per row (built once per data load)."""
    cols = [c for c in columns if c in df.columns]
    if df.empty or not cols:
        return pd.Series("", index=df.index, dtype=str)
    return df[cols].fillna("").astype(str).agg(" ".join, axis=1).str.lower()


def apply_text_filter(df: pd.DataFrame, haystack: pd.Series, text: str) -> pd.DataFrame:
    """Rows whose haystack contains ``text`` (vectorised, case-insensitive)."""
    text = text.strip().lower()
    if not text or df.empty:
        return df
    return df[haystack.str.contains(text, regex=False)]
