"""Shared, cached view of the database for all GUI pages.

Pages used to query SQLite (and rebuild charts) every time they were shown,
each with a different row limit. The store reads once per data version, so
every page sees the same rows and navigation is instant.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from src import database

ROW_LIMIT = 100_000  # effectively "all rows" for this application's scale


class DataStore:
    def __init__(self) -> None:
        self.version = 0
        self._flights: Optional[pd.DataFrame] = None
        self._airports: Optional[pd.DataFrame] = None
        self._info: Optional[dict] = None

    def invalidate(self) -> None:
        """Call after the database changed (refresh finished)."""
        self.version += 1
        self._flights = self._airports = self._info = None

    def flights(self) -> pd.DataFrame:
        if self._flights is None:
            self._flights = database.fetch_flights(limit=ROW_LIMIT)
        return self._flights

    def airports(self) -> pd.DataFrame:
        if self._airports is None:
            self._airports = database.fetch_airports()
        return self._airports

    def info(self) -> dict:
        if self._info is None:
            self._info = database.database_info()
        return self._info
