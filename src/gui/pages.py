"""All application pages. Each page only presents data; business logic stays
in the shared ``src`` modules."""

from __future__ import annotations

import platform
import re
from typing import List, Optional, Sequence, Tuple

import pandas as pd
from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from src import (
    APP_NAME, __version__, analytics, api_client, config, database,
    palette as P, service, utils,
)

from . import icons
from .tables import DataTable, apply_text_filter, search_haystack
from .theme import SP_LG, SP_MD, SP_SM, repolish
from .widgets import (
    Card, ChartCard, ElidedLabel, EmptyState, KpiCard, PageBase,
    ResponsiveGrid, labelled, soft_path,
)

ACCENTS = [P.COBALT, P.TEAL, "#C48A1B", P.NAVY_SOFT, "#6F86A8"]


def _kpis(specs: Sequence[Tuple[str, str]], min_w: int = 200) -> Tuple[ResponsiveGrid, List[KpiCard]]:
    grid = ResponsiveGrid(min_item_width=min_w, max_columns=len(specs))
    cards = []
    for i, (label, accent) in enumerate(specs):
        card = KpiCard(label, accent)
        grid.add(card)
        cards.append(card)
    return grid, cards


def _primary_button(text: str, icon_name: Optional[str] = None) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("primary")
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if icon_name:
        btn.setIcon(icons.icon(icon_name, "#FFFFFF", size=16))
    return btn


def _plain_button(text: str, icon_name: Optional[str] = None) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if icon_name:
        btn.setIcon(icons.icon(icon_name, P.TEXT, size=16))
    return btn


def _set_invalid(widget: QLineEdit, invalid: bool) -> None:
    widget.setProperty("invalid", invalid)
    repolish(widget)


# ---------------------------------------------------------------------------
class OverviewPage(PageBase):
    title = "Overview"
    subtitle = "Executive summary of the stored aviation dataset"

    def __init__(self, main):
        super().__init__(main)
        grid, cards = _kpis([
            ("Total flights", ACCENTS[0]), ("Scheduled / active", ACCENTS[1]),
            ("Delayed", ACCENTS[2]), ("Airports covered", ACCENTS[3]),
            ("Average delay", ACCENTS[4]),
        ], min_w=190)
        (self.card_flights, self.card_active, self.card_delayed,
         self.card_airports, self.card_delay) = cards
        self.body.addWidget(grid)

        self.row = ResponsiveGrid(min_item_width=400, max_columns=2)
        self.donut = ChartCard("status", "Flight status mix", 250)
        self.row.add(self.donut)
        side = Card()
        side.add_title("Quick actions")
        for label, target, ico in [
            ("Explore flights", "explorer", "explorer"),
            ("Flight analytics", "flight_analytics", "flights"),
            ("Airport analytics", "airport_analytics", "airports"),
            ("Delay analysis", "delays", "delays"),
            ("Manage data", "data", "data"),
        ]:
            btn = _plain_button(label, ico)
            btn.setStyleSheet("text-align: left;")
            btn.clicked.connect(lambda _=False, t=target: self.main.navigate(t))
            side.body.addWidget(btn)
        side.body.addStretch(1)
        self.last_label = QLabel("")
        self.last_label.setObjectName("muted")
        self.last_label.setWordWrap(True)
        side.body.addWidget(self.last_label)
        self.row.add(side)
        self.body.addWidget(self.row)

        self.empty_state = EmptyState(
            "No flight data yet",
            "Retrieve flights from AviationStack to populate the dashboard. "
            "Make sure your API key is set in Settings first.",
            "Retrieve flights now", lambda: self.main.start_refresh(),
        )
        self.body.addWidget(self.empty_state)
        self.body.addStretch(1)

    def reload(self) -> None:
        if not self.needs_reload():
            return
        store = self.main.store
        info, df = store.info(), store.flights()
        has_data = info["flights"] > 0
        self.empty_state.setVisible(not has_data)
        self.row.setVisible(has_data)
        self.card_flights.set_value(utils.format_number(info["flights"]), "records in database")
        self.card_airports.set_value(utils.format_number(info["airports"]), "airports observed")
        if has_data:
            sched = int(df["flight_status"].isin(["scheduled", "active"]).sum())
            self.card_active.set_value(utils.format_number(sched), "upcoming or airborne")
            delays = analytics.delay_statistics(df)
            if delays.get("available"):
                self.card_delayed.set_value(
                    utils.format_number(delays["delayed_flights"]),
                    f"{delays['delayed_share_pct']}% of stored flights")
                self.card_delay.set_value(f"{delays['avg_delay_min']} min",
                                          f"median {delays['median_delay_min']} min")
            else:
                self.card_delayed.set_value("0", "delay data unavailable")
                self.card_delay.set_value("n/a", delays.get("reason", ""))
            self.donut.render(df)
        else:
            for c in (self.card_active, self.card_delayed, self.card_delay):
                c.set_value("\u2013", "no data")
        last, status = info.get("last_success"), info.get("last_refresh_status")
        extra = f"\nLatest attempt: {status}" if status and status != "success" else ""
        self.last_label.setText(f"Last successful refresh:\n{last or 'never'}{extra}")
        self.mark_loaded()


# ---------------------------------------------------------------------------
class FlightAnalyticsPage(PageBase):
    title = "Flight Analytics"
    subtitle = "Status mix, airline activity, scheduling and live traffic"

    def __init__(self, main):
        super().__init__(main)
        grid, cards = _kpis([("Airlines", ACCENTS[0]), ("Routes", ACCENTS[1]),
                             ("Codeshared", ACCENTS[3]), ("Live tracked", ACCENTS[4])])
        self.card_airlines, self.card_routes, self.card_codeshare, self.card_live = cards
        self.body.addWidget(grid)
        charts = ResponsiveGrid(min_item_width=420, max_columns=2)
        self.charts = [
            ChartCard("status", "Status distribution"),
            ChartCard("airlines", "Top airlines"),
            ChartCard("dep_hours", "Departures by hour (UTC)"),
            ChartCard("live_map", "Live flight positions"),
        ]
        for c in self.charts:
            charts.add(c)
        self.body.addWidget(charts)
        self.body.addStretch(1)

    def reload(self) -> None:
        if not self.needs_reload():
            return
        df = self.main.store.flights()
        uniq = analytics.unique_value_counts(df)
        cs = analytics.codeshare_share(df)
        live = int(df["live_latitude"].notna().sum()) if "live_latitude" in df else 0
        self.card_airlines.set_value(utils.format_number(uniq["airlines"]), "distinct carriers")
        self.card_routes.set_value(utils.format_number(uniq["routes"]), "departure \u2192 arrival pairs")
        self.card_codeshare.set_value(utils.format_number(cs["codeshared"]), f"{cs['share_pct']}% of flights")
        self.card_live.set_value(utils.format_number(live), "aircraft positions")
        for chart in self.charts:
            chart.render(df)
        self.mark_loaded()


# ---------------------------------------------------------------------------
class AirportAnalyticsPage(PageBase):
    title = "Airport Analytics"
    subtitle = "Airports observed inside stored flight records"
    SEARCH_COLUMNS = ["airport_name", "iata", "icao", "timezone"]
    TABLE_COLUMNS = ["iata", "icao", "airport_name", "timezone", "departures", "arrivals", "sightings"]

    def __init__(self, main):
        super().__init__(main)
        grid, cards = _kpis([("Airports", ACCENTS[1]), ("Busiest airport", ACCENTS[2]),
                             ("Departure sightings", ACCENTS[0]), ("Arrival sightings", ACCENTS[3])])
        self.card_total, self.card_busiest, self.card_deps, self.card_arrs = cards
        self.body.addWidget(grid)
        charts = ResponsiveGrid(min_item_width=420, max_columns=2)
        self.chart_dep = ChartCard("dep_airports", "Top departure airports")
        self.chart_arr = ChartCard("arr_airports", "Top arrival airports")
        charts.add(self.chart_dep)
        charts.add(self.chart_arr)
        self.body.addWidget(charts)

        card = Card()
        head = QHBoxLayout()
        title = QLabel("All observed airports")
        title.setObjectName("cardTitle")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search name or IATA code")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(160)
        self.search.setMaximumWidth(300)
        self.search.setAccessibleName("Search airports")
        head.addWidget(title, 1)
        head.addWidget(self.search, 2)
        card.body.addLayout(head)
        self.table = DataTable("No airports yet. Retrieve flight data to see them here.")
        self.table.setMinimumHeight(260)
        card.body.addWidget(self.table)
        note = QLabel("Airport records are derived from the departure and arrival details inside "
                      "each stored flight - the free AviationStack plan does not expose a "
                      "separate airports directory.")
        note.setObjectName("cardNote")
        note.setWordWrap(True)
        card.body.addWidget(note)
        self.body.addWidget(card)
        self.body.addStretch(1)

        self._airports = pd.DataFrame()
        self._hay = pd.Series(dtype=str)
        self._timer = QTimer(self, singleShot=True, interval=180)
        self._timer.timeout.connect(self._filter)
        self.search.textChanged.connect(lambda _t: self._timer.start())

    def reload(self) -> None:
        if not self.needs_reload():
            return
        flights, airports = self.main.store.flights(), self.main.store.airports()
        self._airports = airports
        self._hay = search_haystack(airports, self.SEARCH_COLUMNS)
        self._filter()
        self.chart_dep.render(flights)
        self.chart_arr.render(flights)
        self.card_total.set_value(utils.format_number(len(airports)), "distinct airports")
        if not airports.empty:
            top = airports.iloc[0]
            self.card_busiest.set_value(top["iata"], utils.truncate(top["airport_name"], 28))
            self.card_deps.set_value(utils.format_number(int(airports["departures"].sum())), "departures seen")
            self.card_arrs.set_value(utils.format_number(int(airports["arrivals"].sum())), "arrivals seen")
        else:
            for c in (self.card_busiest, self.card_deps, self.card_arrs):
                c.set_value("\u2013", "no data")
        self.mark_loaded()

    def _filter(self) -> None:
        text = self.search.text()
        df = apply_text_filter(self._airports, self._hay, text)
        self.table.set_empty_text("No airports match your search." if text.strip() and not self._airports.empty
                                  else "No airports yet. Retrieve flight data to see them here.")
        self.table.set_frame(df, self.TABLE_COLUMNS)


# ---------------------------------------------------------------------------
class FlightExplorerPage(PageBase):
    title = "Flight Explorer"
    subtitle = "Search, filter and inspect every stored flight"
    scrolls = False
    VISIBLE_COLUMNS = [
        "flight_date", "flight_iata", "airline_name", "flight_status",
        "dep_iata", "dep_airport", "dep_scheduled",
        "arr_iata", "arr_airport", "arr_scheduled",
        "dep_delay_min", "arr_delay_min", "route", "is_codeshared",
    ]

    def __init__(self, main):
        super().__init__(main)
        filters = Card()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search flights, airlines, airports, routes")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search flights")
        filters.body.addWidget(self.search)
        grid = ResponsiveGrid(min_item_width=150, max_columns=4, spacing=SP_MD)
        self.status = QComboBox()
        self.status.addItem("All statuses", "")
        for s in api_client.FILTERABLE_STATUSES:
            self.status.addItem(s.title(), s)
        self.dep = QLineEdit()
        self.dep.setPlaceholderText("e.g. LHR")
        self.dep.setMaxLength(4)
        self.arr = QLineEdit()
        self.arr.setPlaceholderText("e.g. JFK")
        self.arr.setMaxLength(4)
        grid.add(labelled("Status", self.status))
        grid.add(labelled("From (IATA)", self.dep))
        grid.add(labelled("To (IATA)", self.arr))
        self.delayed = QCheckBox("Delayed only")
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 18, 0, 0)
        hl.addWidget(self.delayed)
        grid.add(holder)
        filters.body.addWidget(grid)
        foot = QHBoxLayout()
        self.count_label = QLabel("")
        self.count_label.setObjectName("muted")
        clear = _plain_button("Clear filters", "clear")
        clear.clicked.connect(self._clear)
        foot.addWidget(self.count_label, 1)
        foot.addWidget(clear)
        filters.body.addLayout(foot)
        self.body.addWidget(filters)

        self.table = DataTable("No flights match the current filters.")
        self.table.setMinimumHeight(240)
        self.body.addWidget(self.table, 1)

        self.df = pd.DataFrame()
        self._hay = pd.Series(dtype=str)
        self._timer = QTimer(self, singleShot=True, interval=180)
        self._timer.timeout.connect(self._apply)
        self.search.textChanged.connect(lambda _t: self._timer.start())
        self.dep.textChanged.connect(lambda _t: self._timer.start())
        self.arr.textChanged.connect(lambda _t: self._timer.start())
        self.status.currentIndexChanged.connect(lambda _i: self._apply())
        self.delayed.stateChanged.connect(lambda _s: self._apply())

    def set_global_search(self, text: str) -> None:
        """Used by the header search field."""
        self.search.setText(text)
        self._timer.stop()
        self._apply()

    def focus_search(self) -> None:
        self.search.setFocus()

    def reload(self) -> None:
        if not self.needs_reload():
            return
        self.df = self.main.store.flights()
        self._hay = search_haystack(self.df, self.VISIBLE_COLUMNS)
        self._apply()
        self.mark_loaded()

    def _apply(self) -> None:
        df = self.df
        status = self.status.currentData()
        if status and "flight_status" in df:
            df = df[df["flight_status"] == status]
        for box, col in ((self.dep, "dep_iata"), (self.arr, "arr_iata")):
            code = box.text().strip().upper()
            if code and col in df:
                df = df[df[col].fillna("").str.upper() == code]
        if self.delayed.isChecked() and "max_delay_min" in df:
            df = df[df["max_delay_min"].fillna(0) > 0]
        df = apply_text_filter(df, self._hay.reindex(df.index, fill_value=""), self.search.text())
        total = len(self.df)
        self.table.set_empty_text(
            "No flights stored yet. Use Refresh to retrieve data." if total == 0
            else "No flights match the current filters.")
        self.table.set_frame(df, self.VISIBLE_COLUMNS)
        self.count_label.setText(f"{len(df):,} of {total:,} flights")

    def _clear(self) -> None:
        for box in (self.search, self.dep, self.arr):
            box.blockSignals(True)
            box.clear()
            box.blockSignals(False)
        self.status.blockSignals(True)
        self.status.setCurrentIndex(0)
        self.status.blockSignals(False)
        self.delayed.blockSignals(True)
        self.delayed.setChecked(False)
        self.delayed.blockSignals(False)
        self._apply()


# ---------------------------------------------------------------------------
class DelayAnalysisPage(PageBase):
    title = "Delay Analysis"
    subtitle = "How often - and how badly - flights run late"
    TABLE_COLUMNS = ["flight_date", "flight_iata", "airline_name", "flight_status", "dep_iata",
                     "arr_iata", "dep_scheduled", "dep_delay_min", "arr_delay_min", "max_delay_min"]

    def __init__(self, main):
        super().__init__(main)
        grid, cards = _kpis([("Delayed flights", "#C48A1B"), ("Delayed share", "#B8483D"),
                             ("Average delay", ACCENTS[0]), ("Worst delay", ACCENTS[3])])
        self.card_delayed, self.card_share, self.card_avg, self.card_max = cards
        self.body.addWidget(grid)
        row = ResponsiveGrid(min_item_width=400, max_columns=2)
        self.chart = ChartCard("delays", "Delay distribution", 250)
        row.add(self.chart)
        note = Card()
        note.add_title("About delay causes")
        body = QLabel(
            "Delay minutes are reported by the aviation data provider.\n\n"
            "The free data tier does not include delay reasons, so this application never "
            "attributes a delay to weather unless the source explicitly confirms it.\n\n"
            "Weather Alerts appear in the status bar only when confirmed by the data feed "
            "- never guessed.")
        body.setObjectName("muted")
        body.setWordWrap(True)
        note.body.addWidget(body)
        note.body.addStretch(1)
        row.add(note)
        self.body.addWidget(row)
        table_card = Card()
        table_card.add_title("Flights with reported delays")
        self.table = DataTable("No delayed flights in the stored data.")
        self.table.setMinimumHeight(260)
        table_card.body.addWidget(self.table)
        self.body.addWidget(table_card)
        self.body.addStretch(1)

    def reload(self) -> None:
        if not self.needs_reload():
            return
        df = self.main.store.flights()
        stats = analytics.delay_statistics(df)
        delayed_df = df[df["max_delay_min"].fillna(0) > 0] if "max_delay_min" in df and not df.empty else df.iloc[0:0]
        self.table.set_frame(delayed_df, self.TABLE_COLUMNS)
        self.chart.render(df)
        if stats.get("available"):
            self.card_delayed.set_value(utils.format_number(stats["delayed_flights"]), f"of {len(df):,} flights")
            self.card_share.set_value(f"{stats['delayed_share_pct']}%", "report a delay")
            self.card_avg.set_value(f"{stats['avg_delay_min']} min", f"median {stats['median_delay_min']} min")
            self.card_max.set_value(f"{stats['max_delay_min']:.0f} min", "longest reported")
        else:
            for c in (self.card_delayed, self.card_share, self.card_avg, self.card_max):
                c.set_value("\u2013", stats.get("reason", "no data"))
        self.mark_loaded()


# ---------------------------------------------------------------------------
class WeatherInsightsPage(PageBase):
    title = "Weather Insights"
    subtitle = "Context weather for your location and live flights"

    def __init__(self, main):
        super().__init__(main)
        loc = Card()
        loc.add_title("Monitored location")
        self.loc_value = QLabel("")
        self.loc_value.setStyleSheet("font-size: 18px; font-weight: 700;")
        self.loc_detail = QLabel("")
        self.loc_detail.setObjectName("muted")
        self.loc_detail.setWordWrap(True)
        loc.body.addWidget(self.loc_value)
        loc.body.addWidget(self.loc_detail)
        self.body.addWidget(loc)

        card = Card()
        card.add_title("Weather near live-tracked flights",
                       "Current conditions at the reported positions of airborne flights "
                       "(Open-Meteo, informational only).")
        self.wx_container = QVBoxLayout()
        self.wx_container.setSpacing(0)
        card.body.addLayout(self.wx_container)
        self.wx_empty = QLabel("No live-tracked flights in the dataset right now. Positions appear "
                               "only for aircraft the API tracks in real time.")
        self.wx_empty.setObjectName("muted")
        self.wx_empty.setWordWrap(True)
        card.body.addWidget(self.wx_empty)
        refresh = _plain_button("Refresh weather", "refresh")
        refresh.clicked.connect(self._force_reload)
        card.body.addWidget(refresh, alignment=Qt.AlignmentFlag.AlignLeft)
        self.body.addWidget(card)
        self.body.addStretch(1)

    def _force_reload(self) -> None:
        self._loaded_version = -1
        self.reload(force=True)

    def reload(self, force: bool = False) -> None:  # weather is time-sensitive: refresh on each visit
        if (config.ENABLE_WEATHER_LOOKUP and config.WEATHER_LATITUDE and config.WEATHER_LONGITUDE):
            self.loc_value.setText(config.WEATHER_LABEL or "Monitored location")
            try:
                lat, lon = float(config.WEATHER_LATITUDE), float(config.WEATHER_LONGITUDE)
            except ValueError:
                self.loc_detail.setText("The coordinates saved in Settings are not valid numbers.")
            else:
                self.loc_detail.setText("Fetching current weather\u2026")
                self.main.tasks.submit(
                    api_client.fetch_weather, owner=self.loc_detail, latitude=lat, longitude=lon,
                    on_done=lambda wx: self.loc_detail.setText(
                        api_client.weather_summary(wx) if wx else "Weather unavailable right now."),
                    on_error=lambda _e: self.loc_detail.setText("Weather lookup failed."))
        else:
            self.loc_value.setText("Not configured")
            self.loc_detail.setText("Add latitude and longitude in Settings (and enable the weather "
                                    "lookup) to monitor a location.")
        df = self.main.store.flights()
        while self.wx_container.count():
            item = self.wx_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        live = pd.DataFrame()
        if not df.empty and "live_latitude" in df:
            live = df.dropna(subset=["live_latitude", "live_longitude"])
        self.wx_empty.setVisible(live.empty)
        for _, row in live.head(6).iterrows():
            self._add_flight_weather(row)

    def _add_flight_weather(self, row) -> None:
        item = QWidget()
        item.setObjectName("rowItem")
        item.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        hl = QHBoxLayout(item)
        hl.setContentsMargins(0, SP_SM + 2, 0, SP_SM + 2)
        hl.setSpacing(SP_MD)
        name = QLabel(utils.safe_str(row.get("flight_iata"), "Flight"))
        name.setStyleSheet("font-weight: 700;")
        name.setMinimumWidth(70)
        lat, lon = float(row["live_latitude"]), float(row["live_longitude"])
        pos = QLabel(f"{lat:.1f}\u00b0, {lon:.1f}\u00b0")
        pos.setObjectName("muted")
        detail = QLabel("Loading weather\u2026")
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        detail.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hl.addWidget(name)
        hl.addWidget(pos)
        hl.addWidget(detail, 1)
        self.wx_container.addWidget(item)
        self.main.tasks.submit(
            api_client.fetch_weather, owner=detail, latitude=lat, longitude=lon,
            on_done=lambda wx: detail.setText(api_client.weather_summary(wx)),
            on_error=lambda _e: detail.setText("Weather unavailable"))


# ---------------------------------------------------------------------------
_IATA = re.compile(r"^[A-Za-z]{3}$")
_FLIGHT_NO = re.compile(r"^[A-Za-z0-9]{1,8}$")


class DataManagementPage(PageBase):
    title = "Data Management"
    subtitle = "Retrieve fresh data, inspect storage and export records"
    always_reload = True

    def __init__(self, main):
        super().__init__(main)
        card = Card()
        card.add_title("Retrieve data from AviationStack")
        form = ResponsiveGrid(min_item_width=200, max_columns=3, spacing=SP_LG)
        self.limit = QSpinBox()
        self.limit.setRange(1, config.MAX_RECORD_LIMIT)
        self.limit.setValue(config.DEFAULT_RECORD_LIMIT)
        self.limit.setAccessibleName("Number of records")
        self.limit.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.limit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.f_status = QComboBox()
        self.f_status.addItem("Any status", "")
        for s in api_client.FILTERABLE_STATUSES:
            self.f_status.addItem(s.title(), s)
        self.f_dep, self.f_arr = QLineEdit(), QLineEdit()
        self.f_dep.setPlaceholderText("e.g. LHR")
        self.f_arr.setPlaceholderText("e.g. JFK")
        for box in (self.f_dep, self.f_arr):
            box.setMaxLength(3)
        self.f_airline, self.f_number = QLineEdit(), QLineEdit()
        self.f_airline.setPlaceholderText("e.g. Emirates")
        self.f_number.setPlaceholderText("e.g. 201")
        self.f_number.setMaxLength(8)
        form.add(labelled("Records (1-%d)" % config.MAX_RECORD_LIMIT, self.limit))
        form.add(labelled("Status", self.f_status))
        form.add(labelled("Departure airport (IATA)", self.f_dep))
        form.add(labelled("Arrival airport (IATA)", self.f_arr))
        form.add(labelled("Airline name", self.f_airline))
        form.add(labelled("Flight number", self.f_number))
        card.body.addWidget(form)
        hint = QLabel("Free AviationStack plans usually allow up to 100 records per request; "
                      "asking for more may be rejected by the API.")
        hint.setObjectName("cardNote")
        hint.setWordWrap(True)
        card.body.addWidget(hint)
        row = QHBoxLayout()
        self.retrieve_btn = _primary_button("Retrieve flights", "refresh")
        self.retrieve_btn.clicked.connect(self._retrieve)
        row.addWidget(self.retrieve_btn)
        row.addStretch(1)
        card.body.addLayout(row)
        self.retrieve_status = QLabel("")
        self.retrieve_status.setObjectName("muted")
        self.retrieve_status.setWordWrap(True)
        self.retrieve_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.body.addWidget(self.retrieve_status)
        self.body.addWidget(card)

        row2 = ResponsiveGrid(min_item_width=340, max_columns=2)
        db_card = Card()
        db_card.add_title("Local database")
        self.db_grid = QGridLayout()
        self.db_grid.setHorizontalSpacing(SP_LG)
        self.db_grid.setVerticalSpacing(SP_SM)
        self.db_grid.setColumnStretch(1, 1)
        self._db_values = {}
        for i, key in enumerate(["File", "Size", "Flights", "Airports", "Last refresh", "Last success"]):
            k = QLabel(key)
            k.setObjectName("muted")
            v = ElidedLabel("", Qt.TextElideMode.ElideMiddle)
            self.db_grid.addWidget(k, i, 0)
            self.db_grid.addWidget(v, i, 1)
            self._db_values[key] = v
        db_card.body.addLayout(self.db_grid)
        self.db_attempt = QLabel("")
        self.db_attempt.setObjectName("muted")
        self.db_attempt.setWordWrap(True)
        db_card.body.addWidget(self.db_attempt)
        db_card.body.addStretch(1)
        row2.add(db_card)

        ex = Card()
        ex.add_title("Export records")
        for label, table, fmt in [("Flights \u2192 CSV", "flights", "csv"), ("Flights \u2192 JSON", "flights", "json"),
                                  ("Airports \u2192 CSV", "airports", "csv"), ("Airports \u2192 JSON", "airports", "json")]:
            btn = _plain_button(label, "download")
            btn.setStyleSheet("text-align: left;")
            btn.clicked.connect(lambda _=False, t=table, f=fmt: self._export(t, f))
            ex.body.addWidget(btn)
        summary = _plain_button("Analytics summary \u2192 JSON", "download")
        summary.setStyleSheet("text-align: left;")
        summary.clicked.connect(self._export_summary)
        ex.body.addWidget(summary)
        ex.body.addStretch(1)
        row2.add(ex)
        self.body.addWidget(row2)
        self.body.addStretch(1)

    def _validate(self) -> Optional[str]:
        problems = []
        for box, label in ((self.f_dep, "Departure airport"), (self.f_arr, "Arrival airport")):
            bad = bool(box.text().strip()) and not _IATA.match(box.text().strip())
            _set_invalid(box, bad)
            if bad:
                problems.append(f"{label} must be a 3-letter IATA code (for example LHR).")
        bad = bool(self.f_number.text().strip()) and not _FLIGHT_NO.match(self.f_number.text().strip())
        _set_invalid(self.f_number, bad)
        if bad:
            problems.append("Flight number may contain only letters and digits.")
        return " ".join(problems) or None

    def _retrieve(self) -> None:
        error = self._validate()
        if error:
            self.main.notify(error, "warning")
            return
        self.main.start_refresh(
            limit=self.limit.value(),
            flight_status=self.f_status.currentData() or None,
            dep_iata=self.f_dep.text().strip().upper() or None,
            arr_iata=self.f_arr.text().strip().upper() or None,
            airline_name=self.f_airline.text().strip() or None,
            flight_number=self.f_number.text().strip() or None,
        )

    def _export(self, table: str, fmt: str) -> None:
        if database.count_rows(table) == 0:
            self.main.notify(f"The {table} table is empty - retrieve data first.", "warning")
            return
        try:
            path = database.export_table(table, fmt)
            self.main.notify(f"Exported {table} to {soft_path(path)}", "success")
        except Exception as exc:
            self.main.notify(f"Export failed: {exc}", "error")

    def _export_summary(self) -> None:
        df = self.main.store.flights()
        if df.empty:
            self.main.notify("No data to summarise yet - retrieve flights first.", "warning")
            return
        try:
            summary = analytics.full_summary(df, self.main.store.airports())
            path = database.export_summary_json(summary, "analytics_summary")
            self.main.notify(f"Summary exported to {soft_path(path)}", "success")
        except Exception as exc:
            self.main.notify(f"Export failed: {exc}", "error")

    def set_busy(self, busy: bool) -> None:
        self.retrieve_btn.setEnabled(not busy)
        self.retrieve_btn.setText("Retrieving\u2026" if busy else "Retrieve flights")
        if busy:
            self.retrieve_status.setText("Contacting AviationStack\u2026 this can take a few seconds.")

    def set_result(self, result: service.RefreshResult) -> None:
        text = (f"{result.message}\nFetched {result.fetched} \u2022 valid {result.valid} \u2022 "
                f"stored {result.stored} \u2022 airports {result.airports_stored}")
        if result.validation_errors:
            text += "\nValidation issues:\n" + "\n".join(result.validation_errors[:3])
        self.retrieve_status.setText(text)

    def set_error(self, message: str) -> None:
        self.retrieve_status.setText(f"Refresh failed: {message}")

    def reload(self) -> None:
        info = self.main.store.info()
        last = database.last_refresh()
        vals = {
            "File": info["path"], "Size": f"{info['size_kb']} KB",
            "Flights": utils.format_number(info["flights"]),
            "Airports": utils.format_number(info["airports"]),
            "Last refresh": utils.safe_str(info["last_refresh"]),
            "Last success": utils.safe_str(info["last_success"]),
        }
        for key, text in vals.items():
            self._db_values[key].setText(str(text))
        if last and last.get("status") != "success":
            self.db_attempt.setText(f"Latest attempt: {last['status']} - {last.get('message', '')}")
        else:
            self.db_attempt.setText("")


# ---------------------------------------------------------------------------
class SettingsPage(PageBase):
    title = "Settings"
    subtitle = "API key and optional weather context"
    always_reload = True

    def __init__(self, main):
        super().__init__(main)
        api = Card()
        api.add_title("AviationStack API")
        self.key_status = QLabel()
        self.key_status.setObjectName("muted")
        self.key_status.setWordWrap(True)
        self.key_input = QLineEdit()
        self.key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_input.setPlaceholderText("Paste a new API key (leave blank to keep the current one)")
        self.key_input.setAccessibleName("New API key")
        self.show_key = QCheckBox("Show key while typing")
        self.show_key.toggled.connect(lambda on: self.key_input.setEchoMode(
            QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        api.body.addWidget(labelled("Configured key", self.key_status))
        api.body.addWidget(labelled("New API key", self.key_input))
        api.body.addWidget(self.show_key)
        note = QLabel("The key is stored in the .env file at the project root and is never shown in "
                      "full. Get a free key at aviationstack.com.")
        note.setObjectName("cardNote")
        note.setWordWrap(True)
        api.body.addWidget(note)
        self.body.addWidget(api)

        wx = Card()
        wx.add_title("Weather lookup (Open-Meteo, optional)")
        self.weather_enabled = QCheckBox("Enable weather status in the status bar")
        self.weather_label = QLineEdit()
        self.weather_label.setPlaceholderText("Display name, e.g. Home airport")
        self.weather_lat, self.weather_lon = QLineEdit(), QLineEdit()
        self.weather_lat.setPlaceholderText("-90 to 90, e.g. 31.5204")
        self.weather_lon.setPlaceholderText("-180 to 180, e.g. 74.3587")
        wx.body.addWidget(self.weather_enabled)
        wx.body.addWidget(labelled("Location label", self.weather_label))
        coords = ResponsiveGrid(min_item_width=220, max_columns=2, spacing=SP_LG)
        coords.add(labelled("Latitude", self.weather_lat))
        coords.add(labelled("Longitude", self.weather_lon))
        wx.body.addWidget(coords)
        wnote = QLabel("Leave latitude and longitude blank to turn location weather off. Weather is "
                       "shown for context only; delays are attributed to weather only when the flight "
                       "data source confirms it.")
        wnote.setObjectName("cardNote")
        wnote.setWordWrap(True)
        wx.body.addWidget(wnote)
        self.body.addWidget(wx)

        row = QHBoxLayout()
        save = _primary_button("Save settings")
        save.clicked.connect(self._save)
        row.addWidget(save)
        row.addStretch(1)
        self.body.addLayout(row)
        self.body.addStretch(1)

    @staticmethod
    def _parse_coord(box: QLineEdit, low: float, high: float, name: str):
        text = box.text().strip().replace(",", ".")
        if not text:
            _set_invalid(box, False)
            return None, None
        try:
            value = float(text)
            if not low <= value <= high:
                raise ValueError
        except ValueError:
            _set_invalid(box, True)
            return None, f"{name} must be a number between {low:g} and {high:g}."
        _set_invalid(box, False)
        return f"{value:.4f}", None

    def _save(self) -> None:
        errors = []
        values = {}
        key = self.key_input.text().strip()
        if key:
            bad = len(key) < 8 or any(ch.isspace() for ch in key)
            _set_invalid(self.key_input, bad)
            if bad:
                errors.append("The API key looks invalid (at least 8 characters, no spaces).")
            else:
                values["AVIATIONSTACK_API_KEY"] = key
        lat, err = self._parse_coord(self.weather_lat, -90, 90, "Latitude")
        errors += [err] if err else []
        lon, err = self._parse_coord(self.weather_lon, -180, 180, "Longitude")
        errors += [err] if err else []
        if (lat is None) != (lon is None) and not errors:
            errors.append("Enter both latitude and longitude, or leave both blank.")
        if errors:
            self.main.notify(" ".join(errors), "warning")
            return
        values["ENABLE_WEATHER_LOOKUP"] = "1" if self.weather_enabled.isChecked() else "0"
        values["WEATHER_LABEL"] = self.weather_label.text().strip() or "Monitored location"
        values["WEATHER_LATITUDE"] = lat
        values["WEATHER_LONGITUDE"] = lon
        try:
            config.update_env_file(values)
            config.reload_environment()
            self.key_input.clear()
            self.reload()
            self.main.refresh_status_bar()
            self.main.notify("Settings saved.", "success")
        except Exception as exc:
            self.main.notify(f"Could not save settings: {exc}", "error")

    def reload(self) -> None:
        self.key_status.setText(config.masked_api_key() if config.api_key_configured()
                                else "Not configured - data retrieval is unavailable")
        self.weather_enabled.setChecked(config.ENABLE_WEATHER_LOOKUP)
        self.weather_label.setText(config.WEATHER_LABEL)
        self.weather_lat.setText(config.WEATHER_LATITUDE)
        self.weather_lon.setText(config.WEATHER_LONGITUDE)
        for box in (self.key_input, self.weather_lat, self.weather_lon):
            _set_invalid(box, False)


# ---------------------------------------------------------------------------
class AboutPage(PageBase):
    title = "About"
    subtitle = "Application information"

    def __init__(self, main):
        super().__init__(main)
        card = Card()
        head = QHBoxLayout()
        head.setSpacing(SP_MD)
        logo = QLabel()
        icon_path = config.ASSETS_DIR / "icons" / "app.svg"
        if icon_path.exists():
            logo.setPixmap(QIcon(str(icon_path)).pixmap(QSize(44, 44)))
        name = QLabel(f"{APP_NAME}")
        name.setStyleSheet("font-size: 20px; font-weight: 700;")
        ver = QLabel(f"Version {__version__}")
        ver.setObjectName("muted")
        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(name)
        titles.addWidget(ver)
        head.addWidget(logo)
        head.addLayout(titles, 1)
        card.body.addLayout(head)
        desc = QLabel(
            "A desktop and terminal application for retrieving, exploring and analysing flight and "
            "airport information.\n\nPipeline: AviationStack REST API \u2192 Pydantic validation \u2192 pandas "
            "processing \u2192 SQLite storage \u2192 analytics and charts.\n\nWeather context: Open-Meteo "
            "(optional, key-less).\nBuilt with Python, PySide6, pandas, Pydantic, Matplotlib and SQLite.")
        desc.setObjectName("muted")
        desc.setWordWrap(True)
        card.body.addWidget(desc)
        self.body.addWidget(card)

        env = Card()
        env.add_title("Environment")
        import matplotlib
        import PySide6
        grid = QGridLayout()
        grid.setHorizontalSpacing(SP_LG)
        grid.setVerticalSpacing(SP_SM)
        grid.setColumnStretch(1, 1)
        for i, (k, v) in enumerate([
            ("Python", platform.python_version()), ("PySide6", PySide6.__version__),
            ("pandas", pd.__version__), ("Matplotlib", matplotlib.__version__),
            ("Database", str(config.DATABASE_PATH)), ("Log file", str(config.LOG_DIR / "application.log")),
        ]):
            kl = QLabel(k)
            kl.setObjectName("muted")
            vl = ElidedLabel(v, Qt.TextElideMode.ElideMiddle)
            grid.addWidget(kl, i, 0)
            grid.addWidget(vl, i, 1)
        env.body.addLayout(grid)
        self.body.addWidget(env)
        self.body.addStretch(1)
