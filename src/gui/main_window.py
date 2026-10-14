"""Main window: navigation, header, status bar and the refresh workflow."""

from __future__ import annotations

import sys
from typing import Dict, Optional

import pandas as pd
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QProgressBar, QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from src import (
    APP_NAME, __version__, analytics, api_client, config, palette as P, service,
)
from src.utils import get_logger

from . import icons
from .pages import (
    AboutPage, AirportAnalyticsPage, DataManagementPage, DelayAnalysisPage,
    FlightAnalyticsPage, FlightExplorerPage, OverviewPage, SettingsPage,
    WeatherInsightsPage,
)
from .store import DataStore
from .theme import SP_LG, SP_MD, SP_SM, SP_XL, build_stylesheet, repolish
from .widgets import Banner, ElidedLabel
from .workers import TaskRunner

logger = get_logger()

SIDEBAR_WIDE, SIDEBAR_COMPACT = 232, 64
COMPACT_BELOW = 1020        # window width that switches to the icon-only sidebar
HIDE_UPDATED_BELOW = 1180   # window width below which "Updated ..." is hidden


class FlightStatusBar(QFrame):
    """Bottom strip: flight-condition chips, optional weather, last message."""

    CATEGORIES = ["On Time", "Delayed", "Cancelled", "Incident/Diverted",
                  "Weather Alert", "Weather Delay", "Landed", "Status Unknown"]
    ALWAYS = ("On Time", "Delayed", "Cancelled")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(SP_LG, 7, SP_LG, 7)
        self._row.setSpacing(SP_SM)
        self._lead = QLabel("FLIGHT CONDITIONS")
        self._lead.setObjectName("kpiLabel")
        self._row.addWidget(self._lead)
        self._chips: Dict[str, QLabel] = {}
        self._wanted: Dict[str, bool] = {}
        for cat in self.CATEGORIES:
            chip = QLabel(f"{cat}: 0")
            chip.setObjectName("chip")
            color = analytics.STATUS_BAR_COLORS.get(cat, P.TEXT_MUTED)
            chip.setStyleSheet(f"color: {color};")
            chip.hide()
            self._chips[cat] = chip
            self._row.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)
        self.weather_chip = QLabel("")
        self.weather_chip.setObjectName("chip")
        self.weather_chip.setStyleSheet(f"color: {P.COBALT_DARK};")
        self.weather_chip.hide()
        self._row.addWidget(self.weather_chip)
        self._row.addStretch(1)
        self.message = ElidedLabel("Ready")
        self.message.setObjectName("statusMsg")
        self.message.setMinimumWidth(0)
        self.message.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._row.addWidget(self.message, 3)
        self._weather_wanted = False

    def update_conditions(self, df: pd.DataFrame) -> None:
        counts = analytics.condition_counts(df)
        has_data = not df.empty
        for cat, chip in self._chips.items():
            n = counts.get(cat, 0)
            chip.setText(f"{cat}: {n}")
            self._wanted[cat] = has_data and (cat in self.ALWAYS or n > 0)
        self._lead.setToolTip("Condition of every stored flight: " + ", ".join(
            f"{c} {counts.get(c, 0)}" for c in self.CATEGORIES))
        self._fit()

    def set_weather(self, text: Optional[str]) -> None:
        self.weather_chip.setText(text or "")
        self.weather_chip.setToolTip(text or "")
        self._weather_wanted = bool(text)
        self._fit()

    def set_message(self, text: str) -> None:
        self.message.setText(text)

    def _fit(self) -> None:
        """Show as many chips as fit, keeping room for the message."""
        budget = self.width() - 2 * SP_LG - self._lead.sizeHint().width() - 220
        for cat, chip in self._chips.items():
            if not self._wanted.get(cat):
                chip.hide()
                continue
            need = chip.sizeHint().width() + SP_SM
            chip.setVisible(budget >= need)
            budget -= need
        need = self.weather_chip.sizeHint().width() + SP_SM
        self.weather_chip.setVisible(self._weather_wanted and budget >= need)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._fit()


class MainWindow(QMainWindow):
    NAV = [
        ("section", None, "ANALYTICS"),
        ("overview", "overview", "Overview"),
        ("flight_analytics", "flights", "Flight Analytics"),
        ("airport_analytics", "airports", "Airport Analytics"),
        ("explorer", "explorer", "Flight Explorer"),
        ("delays", "delays", "Delay Analysis"),
        ("weather", "weather", "Weather Insights"),
        ("section", None, "SYSTEM"),
        ("data", "data", "Data Management"),
        ("settings", "settings", "Settings"),
        ("about", "about", "About"),
    ]

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1360, 840)
        self.setMinimumSize(860, 560)
        self.store = DataStore()
        self.tasks = TaskRunner(self)
        self._refreshing = False
        self._compact: Optional[bool] = None
        self._wx_token = 0

        root_widget = QWidget()
        root_widget.setObjectName("appRoot")
        self.setCentralWidget(root_widget)
        root = QHBoxLayout(root_widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._build_sidebar(root)
        column = QVBoxLayout()
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        root.addLayout(column, 1)
        self._build_topbar(column)

        self.busy_bar = QProgressBar()
        self.busy_bar.setObjectName("busy")
        self.busy_bar.setRange(0, 0)
        self.busy_bar.setTextVisible(False)
        self.busy_bar.hide()
        column.addWidget(self.busy_bar)

        banner_wrap = QWidget()
        bl = QVBoxLayout(banner_wrap)
        bl.setContentsMargins(SP_XL, SP_MD, SP_XL, 0)
        self.banner = Banner()
        bl.addWidget(self.banner)
        column.addWidget(banner_wrap)
        banner_wrap.setVisible(False)
        self.banner.visibilityChanged.connect(banner_wrap.setVisible)

        self.stack = QStackedWidget()
        self.stack.setObjectName("pageStack")
        column.addWidget(self.stack, 1)
        self.pages = {
            "overview": OverviewPage(self), "flight_analytics": FlightAnalyticsPage(self),
            "airport_analytics": AirportAnalyticsPage(self), "explorer": FlightExplorerPage(self),
            "delays": DelayAnalysisPage(self), "weather": WeatherInsightsPage(self),
            "data": DataManagementPage(self), "settings": SettingsPage(self),
            "about": AboutPage(self),
        }
        for page in self.pages.values():
            self.stack.addWidget(page)
        self.status_bar = FlightStatusBar()
        column.addWidget(self.status_bar)

        self._install_shortcuts()
        self.navigate("overview")
        self.refresh_status_bar()
        self._apply_layout_mode()

    # ---- construction helpers ------------------------------------------------
    def _build_sidebar(self, root: QHBoxLayout) -> None:
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        sb = QVBoxLayout(self.sidebar)
        sb.setContentsMargins(0, 0, 0, SP_LG)
        sb.setSpacing(0)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(SP_LG + 4, SP_XL - 2, SP_LG, SP_MD)
        brand_row.setSpacing(SP_MD)
        self.logo = QLabel()
        icon_path = config.ASSETS_DIR / "icons" / "app.svg"
        if icon_path.exists():
            self.logo.setPixmap(QIcon(str(icon_path)).pixmap(QSize(32, 32)))
        else:
            self.logo.setPixmap(icons.pixmap("flights", "#FFFFFF", 28))
        titles = QVBoxLayout()
        titles.setSpacing(0)
        self.brand = QLabel("SkyLens")
        self.brand.setObjectName("brand")
        self.brand_sub = QLabel("Flight analytics")
        self.brand_sub.setObjectName("brandSub")
        titles.addWidget(self.brand)
        titles.addWidget(self.brand_sub)
        self.brand_titles = QWidget()
        self.brand_titles.setLayout(titles)
        brand_row.addWidget(self.logo)
        brand_row.addWidget(self.brand_titles, 1)
        sb.addLayout(brand_row)
        self._brand_row = brand_row

        self.nav_buttons: Dict[str, QPushButton] = {}
        self._nav_labels: Dict[str, str] = {}
        self._sections = []
        for key, icon_name, label in self.NAV:
            if key == "section":
                sec = QLabel(label)
                sec.setObjectName("navSection")
                self._sections.append(sec)
                sb.addWidget(sec)
                continue
            btn = QPushButton(label)
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.setIcon(icons.icon(icon_name, P.TEXT_ON_DARK_MUTED, "#FFFFFF", 20))
            btn.setIconSize(QSize(20, 20))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setAccessibleName(label)
            btn.clicked.connect(lambda _=False, k=key: self.navigate(k))
            self.nav_buttons[key] = btn
            self._nav_labels[key] = label
            sb.addWidget(btn)
        sb.addStretch(1)
        self.foot = QLabel(f"v{__version__}  \u2022  AviationStack")
        self.foot.setObjectName("navFoot")
        sb.addWidget(self.foot)
        root.addWidget(self.sidebar)

    def _build_topbar(self, column: QVBoxLayout) -> None:
        topbar = QFrame()
        topbar.setObjectName("topbar")
        topbar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        topbar.setFixedHeight(68)
        hl = QHBoxLayout(topbar)
        hl.setContentsMargins(SP_XL, 0, SP_XL, 0)
        hl.setSpacing(SP_MD)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        self.page_title = QLabel("Overview")
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = ElidedLabel("")
        self.page_subtitle.setObjectName("pageSubtitle")
        titles.addWidget(self.page_title)
        titles.addWidget(self.page_subtitle)
        hl.addLayout(titles, 3)

        self.header_search = QLineEdit()
        self.header_search.setPlaceholderText("Search flights (Ctrl+K)")
        self.header_search.setClearButtonEnabled(True)
        self.header_search.setAccessibleName("Search all flights")
        self.header_search.setMinimumWidth(140)
        self.header_search.setMaximumWidth(280)
        self.header_search.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.header_search.returnPressed.connect(self._header_search)
        hl.addWidget(self.header_search, 2, Qt.AlignmentFlag.AlignVCenter)

        self.api_label = QLabel("")
        self.api_label.setObjectName("chip")
        hl.addWidget(self.api_label, 0, Qt.AlignmentFlag.AlignVCenter)
        self.last_updated = QLabel("")
        self.last_updated.setObjectName("updated")
        hl.addWidget(self.last_updated, 0, Qt.AlignmentFlag.AlignVCenter)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("primary")
        self.refresh_btn.setIcon(icons.icon("refresh", "#FFFFFF", size=16))
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setToolTip("Retrieve the latest flights (F5)")
        self.refresh_btn.clicked.connect(lambda: self.start_refresh())
        hl.addWidget(self.refresh_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        column.addWidget(topbar)

    def _install_shortcuts(self) -> None:
        keys = [k for k, _i, _l in self.NAV if k != "section"]
        for i, key in enumerate(keys[:9], start=1):
            sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            sc.activated.connect(lambda k=key: self.navigate(k))
            self.nav_buttons[key].setToolTip(f"{self._nav_labels[key]} (Ctrl+{i})")
        for seq in ("F5", "Ctrl+R"):
            QShortcut(QKeySequence(seq), self).activated.connect(lambda: self.start_refresh())
        QShortcut(QKeySequence("Ctrl+K"), self).activated.connect(self._focus_search)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._focus_search)

    def _focus_search(self) -> None:
        if self._current_key() == "explorer":
            self.pages["explorer"].focus_search()
        else:
            self.header_search.setFocus()
            self.header_search.selectAll()

    # ---- responsive layout -----------------------------------------------------
    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._apply_layout_mode()

    def _apply_layout_mode(self) -> None:
        width = self.width()
        compact = width < COMPACT_BELOW
        self.last_updated.setVisible(width >= HIDE_UPDATED_BELOW)
        if compact == self._compact:
            return
        self._compact = compact
        self.sidebar.setFixedWidth(SIDEBAR_COMPACT if compact else SIDEBAR_WIDE)
        self.brand_titles.setVisible(not compact)
        self.foot.setVisible(not compact)
        m = self._brand_row.contentsMargins()
        self._brand_row.setContentsMargins(16 if compact else SP_LG + 4, m.top(), m.right(), m.bottom())
        for sec in self._sections:
            sec.setVisible(not compact)
        for key, btn in self.nav_buttons.items():
            btn.setText("" if compact else self._nav_labels[key])
            btn.setProperty("compact", compact)
            repolish(btn)

    # ---- navigation ---------------------------------------------------------------
    def navigate(self, key: str) -> None:
        for k, btn in self.nav_buttons.items():
            btn.setChecked(k == key)
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        self.page_title.setText(page.title)
        self.page_subtitle.setText(page.subtitle)
        try:
            page.reload()
        except Exception as exc:
            logger.exception("Page %s failed to load", key)
            self.notify(f"Could not load this page: {exc}", "error")

    def _current_key(self) -> str:
        widget = self.stack.currentWidget()
        for k, p in self.pages.items():
            if p is widget:
                return k
        return "overview"

    def _header_search(self) -> None:
        text = self.header_search.text().strip()
        self.navigate("explorer")
        if text:
            self.pages["explorer"].set_global_search(text)
        self.header_search.clear()

    # ---- refresh workflow ---------------------------------------------------------
    def _set_busy(self, busy: bool) -> None:
        self._refreshing = busy
        self.refresh_btn.setEnabled(not busy)
        self.refresh_btn.setText("Syncing\u2026" if busy else "Refresh")
        self.busy_bar.setVisible(busy)
        self.pages["data"].set_busy(busy)

    def start_refresh(self, **filters) -> None:
        if self._refreshing:
            return
        if not config.api_key_configured():
            self.notify("No API key configured. Add one in Settings to retrieve data.", "warning")
            self.navigate("settings")
            return
        self._set_busy(True)
        self.status_bar.set_message("Retrieving flights from AviationStack\u2026")
        self.tasks.submit(service.refresh_data, on_done=self._refresh_done,
                          on_error=self._refresh_failed, **filters)

    def _refresh_done(self, result: service.RefreshResult) -> None:
        self._set_busy(False)
        self.store.invalidate()
        self.pages["data"].set_result(result)
        self.status_bar.set_message(result.message)
        if not result.success:
            self.notify(result.message, "error")
        elif result.stored == 0:
            self.notify(f"{result.message} No new records were stored.", "warning")
        else:
            self.notify(result.message, "success")
        self.refresh_status_bar()
        try:
            self.pages[self._current_key()].reload()
        except Exception:
            logger.exception("Reload after refresh failed")

    def _refresh_failed(self, message: str) -> None:
        self._set_busy(False)
        self.pages["data"].set_error(message)
        self.status_bar.set_message("Refresh failed")
        self.notify(f"Refresh failed: {message}", "error")

    # ---- header + status bar -------------------------------------------------------
    def _update_api_status(self) -> None:
        ok = config.api_key_configured()
        self.api_label.setText("API key set" if ok else "API key missing")
        self.api_label.setStyleSheet(f"color: {P.SUCCESS if ok else P.ERROR};")
        self.api_label.setToolTip(
            "An API key is configured. The connection itself is checked when data is retrieved."
            if ok else "Open Settings to add your AviationStack API key.")
        try:
            info = self.store.info()
            last = info.get("last_success") or info.get("last_refresh")
        except Exception:
            last = None
        text = f"Updated {last}" if last else "No data retrieved yet"
        self.last_updated.setText(text)
        self.last_updated.setToolTip(text)

    def refresh_status_bar(self) -> None:
        try:
            self.status_bar.update_conditions(self.store.flights())
        except Exception:
            logger.exception("Could not read flights for the status bar")
            self.status_bar.update_conditions(pd.DataFrame())
        self._update_api_status()
        self._wx_token += 1
        token = self._wx_token
        if config.ENABLE_WEATHER_LOOKUP and config.WEATHER_LATITUDE and config.WEATHER_LONGITUDE:
            try:
                lat, lon = float(config.WEATHER_LATITUDE), float(config.WEATHER_LONGITUDE)
            except ValueError:
                self.status_bar.set_weather(None)
                return
            label = config.WEATHER_LABEL

            def _done(weather):
                if token == self._wx_token:  # ignore stale answers
                    self.status_bar.set_weather(
                        f"{label}: {api_client.weather_summary(weather)}" if weather else None)

            self.tasks.submit(api_client.fetch_weather, on_done=_done,
                              on_error=lambda _e: None, owner=self.status_bar,
                              latitude=lat, longitude=lon)
        else:
            self.status_bar.set_weather(None)

    def notify(self, message: str, kind: str = "info") -> None:
        """Show a non-blocking notification (kinds: success/info/warning/error)."""
        if isinstance(kind, bool):  # backwards compatible with notify(msg, error=True)
            kind = "error" if kind else "info"
        self.banner.show_message(message, kind)
        self.status_bar.set_message(message.replace("\u200b", ""))

    def closeEvent(self, event):  # noqa: N802
        # Let in-flight requests finish so no worker thread is destroyed mid-run.
        self.tasks.wait(3000)
        super().closeEvent(event)


def main() -> int:
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(build_stylesheet())
    icon_path = config.ASSETS_DIR / "icons" / "app.svg"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
    window = MainWindow()
    window.show()
    return app.exec()
