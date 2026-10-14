"""SQLite persistence layer for Flight and Airport Analytics.

Both the terminal app and the GUI talk to the database exclusively through
this module. All writes use transactions and parameterized queries; flight
records are deduplicated by a natural key (date + flight IATA + dep/arr IATA)
so refreshing data never creates duplicate rows.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Optional

import pandas as pd

from . import config
from .data_processor import FLIGHT_COLUMNS, UNIQUE_KEY
from .utils import DatabaseError, get_logger, utc_now_iso

logger = get_logger()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS flights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    flight_date TEXT,
    flight_status TEXT,
    flight_iata TEXT,
    flight_icao TEXT,
    flight_number TEXT,
    airline_name TEXT,
    airline_iata TEXT,
    airline_icao TEXT,
    dep_airport TEXT,
    dep_iata TEXT,
    dep_icao TEXT,
    dep_terminal TEXT,
    dep_gate TEXT,
    dep_delay_min REAL,
    dep_scheduled TEXT,
    dep_estimated TEXT,
    dep_actual TEXT,
    dep_timezone TEXT,
    arr_airport TEXT,
    arr_iata TEXT,
    arr_icao TEXT,
    arr_terminal TEXT,
    arr_gate TEXT,
    arr_baggage TEXT,
    arr_delay_min REAL,
    arr_scheduled TEXT,
    arr_estimated TEXT,
    arr_actual TEXT,
    arr_timezone TEXT,
    aircraft_registration TEXT,
    aircraft_icao24 TEXT,
    is_codeshared INTEGER DEFAULT 0,
    live_latitude REAL,
    live_longitude REAL,
    live_altitude REAL,
    live_speed_kmh REAL,
    live_is_ground INTEGER,
    route TEXT,
    is_delayed INTEGER DEFAULT 0,
    max_delay_min REAL,
    retrieved_at TEXT,
    UNIQUE(flight_date, flight_iata, dep_iata, arr_iata)
        ON CONFLICT REPLACE
);

CREATE TABLE IF NOT EXISTS airports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    iata TEXT UNIQUE NOT NULL,
    icao TEXT,
    airport_name TEXT,
    timezone TEXT,
    departures INTEGER DEFAULT 0,
    arrivals INTEGER DEFAULT 0,
    sightings INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS refresh_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    refreshed_at TEXT NOT NULL,
    source TEXT,
    records_fetched INTEGER,
    records_valid INTEGER,
    records_stored INTEGER,
    status TEXT,
    message TEXT
);

CREATE INDEX IF NOT EXISTS idx_flights_status ON flights(flight_status);
CREATE INDEX IF NOT EXISTS idx_flights_airline ON flights(airline_name);
CREATE INDEX IF NOT EXISTS idx_flights_dep ON flights(dep_iata);
CREATE INDEX IF NOT EXISTS idx_flights_arr ON flights(arr_iata);
"""


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Open a connection (creating the schema on first use)."""
    path = Path(db_path) if db_path else config.DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(_SCHEMA)
        return conn
    except sqlite3.Error as exc:
        raise DatabaseError(f"Cannot open database {path}: {exc}")


def _serializable(value):
    """Convert pandas/NaT values into SQLite-friendly scalars."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalar
        return value.item()
    if isinstance(value, bool):
        return int(value)
    return value


def insert_flights(df: pd.DataFrame, db_path: Optional[Path] = None) -> int:
    """Upsert flight rows; returns the number of rows written."""
    if df.empty:
        return 0
    columns = [c for c in FLIGHT_COLUMNS if c in df.columns]
    placeholders = ", ".join("?" for _ in columns)
    sql = (
        f"INSERT INTO flights ({', '.join(columns)}) "
        f"VALUES ({placeholders})"
    )
    # SQLite treats NULLs as distinct inside UNIQUE constraints, so the
    # natural-key columns are coerced to '' to keep deduplication reliable.
    rows = []
    for row in df[columns].itertuples(index=False, name=None):
        values = [_serializable(v) for v in row]
        for idx, col in enumerate(columns):
            if col in UNIQUE_KEY and values[idx] is None:
                values[idx] = ""
        rows.append(tuple(values))
    try:
        with get_connection(db_path) as conn:
            conn.executemany(sql, rows)
        return len(rows)
    except sqlite3.Error as exc:
        raise DatabaseError(f"Failed to insert flights: {exc}")


def insert_airports(df: pd.DataFrame, db_path: Optional[Path] = None) -> int:
    """Upsert derived airport rows (merge sighting counters)."""
    if df.empty:
        return 0
    sql = """
        INSERT INTO airports (iata, icao, airport_name, timezone,
                              departures, arrivals, sightings)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(iata) DO UPDATE SET
            icao = COALESCE(excluded.icao, airports.icao),
            airport_name = COALESCE(excluded.airport_name, airports.airport_name),
            timezone = COALESCE(excluded.timezone, airports.timezone),
            departures = excluded.departures,
            arrivals = excluded.arrivals,
            sightings = excluded.sightings
    """
    rows = [
        (
            _serializable(r.iata),
            _serializable(r.icao),
            _serializable(r.airport_name),
            _serializable(r.timezone),
            int(r.departures),
            int(r.arrivals),
            int(r.sightings),
        )
        for r in df.itertuples(index=False)
        if pd.notna(r.iata)
    ]
    try:
        with get_connection(db_path) as conn:
            conn.executemany(sql, rows)
        return len(rows)
    except sqlite3.Error as exc:
        raise DatabaseError(f"Failed to insert airports: {exc}")


def log_refresh(
    source: str,
    fetched: int,
    valid: int,
    stored: int,
    status: str,
    message: str = "",
    db_path: Optional[Path] = None,
) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """INSERT INTO refresh_log
               (refreshed_at, source, records_fetched, records_valid,
                records_stored, status, message)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (utc_now_iso(), source, fetched, valid, stored, status, message),
        )


def last_refresh(db_path: Optional[Path] = None) -> Optional[dict]:
    """Most recent refresh-log entry, or None."""
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM refresh_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def last_successful_refresh(db_path: Optional[Path] = None) -> Optional[dict]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM refresh_log WHERE status = 'success' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def _query(sql: str, params: tuple = (), db_path: Optional[Path] = None) -> pd.DataFrame:
    try:
        with get_connection(db_path) as conn:
            return pd.read_sql_query(sql, conn, params=params)
    except sqlite3.Error as exc:
        raise DatabaseError(f"Query failed: {exc}")


def fetch_flights(
    status: Optional[str] = None,
    airline: Optional[str] = None,
    dep_iata: Optional[str] = None,
    arr_iata: Optional[str] = None,
    search: Optional[str] = None,
    search_fields: Optional[List[str]] = None,
    delayed_only: bool = False,
    limit: int = 5000,
    db_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Retrieve flights with optional server-side filters."""
    clauses, params = [], []
    if status:
        clauses.append("flight_status = ?")
        params.append(status.lower())
    if airline:
        clauses.append("(airline_name LIKE ? OR airline_iata LIKE ?)")
        params += [f"%{airline}%", f"%{airline}%"]
    if dep_iata:
        clauses.append("dep_iata = ?")
        params.append(dep_iata.upper())
    if arr_iata:
        clauses.append("arr_iata = ?")
        params.append(arr_iata.upper())
    if delayed_only:
        clauses.append("COALESCE(max_delay_min, 0) > 0")
    if search:
        fields = search_fields or [
            "flight_iata", "flight_number", "airline_name",
            "dep_airport", "dep_iata", "arr_airport", "arr_iata", "route",
        ]
        safe = [f for f in fields if f in FLIGHT_COLUMNS]
        if safe:
            clauses.append("(" + " OR ".join(f"{f} LIKE ?" for f in safe) + ")")
            params += [f"%{search}%"] * len(safe)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(int(limit))
    return _query(
        f"SELECT * FROM flights {where} ORDER BY flight_date DESC, id DESC "
        f"LIMIT ?",
        tuple(params),
        db_path,
    )


def fetch_airports(db_path: Optional[Path] = None) -> pd.DataFrame:
    return _query(
        "SELECT * FROM airports ORDER BY sightings DESC", (), db_path
    )


def count_rows(table: str, db_path: Optional[Path] = None) -> int:
    if table not in {"flights", "airports", "refresh_log"}:
        raise ValueError(f"Unsupported table {table}")
    with get_connection(db_path) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def distinct_values(column: str, db_path: Optional[Path] = None) -> List[str]:
    if column not in FLIGHT_COLUMNS:
        return []
    rows = _query(
        f"SELECT DISTINCT {column} AS v FROM flights "
        f"WHERE {column} IS NOT NULL ORDER BY v",
        (),
        db_path,
    )
    return rows["v"].tolist()


def database_info(db_path: Optional[Path] = None) -> dict:
    path = Path(db_path) if db_path else config.DATABASE_PATH
    info = {
        "path": str(path),
        "exists": path.exists(),
        "size_kb": round(path.stat().st_size / 1024, 1) if path.exists() else 0,
        "flights": 0,
        "airports": 0,
        "refreshes": 0,
        "last_refresh": None,
        "last_success": None,
    }
    if path.exists():
        info["flights"] = count_rows("flights", path)
        info["airports"] = count_rows("airports", path)
        info["refreshes"] = count_rows("refresh_log", path)
        last = last_refresh(path)
        last_ok = last_successful_refresh(path)
        info["last_refresh"] = last["refreshed_at"] if last else None
        info["last_refresh_status"] = last["status"] if last else None
        info["last_success"] = last_ok["refreshed_at"] if last_ok else None
    return info


def export_table(
    table: str,
    fmt: str = "csv",
    out_dir: Optional[Path] = None,
    db_path: Optional[Path] = None,
) -> Path:
    """Export a table to CSV or JSON under ``data/processed/`` by default."""
    from .utils import timestamp_for_filename

    df = fetch_flights(db_path=db_path) if table == "flights" else fetch_airports(db_path)
    out_dir = Path(out_dir) if out_dir else config.DATA_PROCESSED_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    fmt = fmt.lower()
    if fmt == "csv":
        path = out_dir / f"{table}_export_{timestamp_for_filename()}.csv"
        df.to_csv(path, index=False)
    elif fmt == "json":
        path = out_dir / f"{table}_export_{timestamp_for_filename()}.json"
        path.write_text(
            df.to_json(orient="records", indent=2, force_ascii=False),
            encoding="utf-8",
        )
    else:
        raise ValueError("fmt must be 'csv' or 'json'")
    return path


def clear_flights(db_path: Optional[Path] = None) -> None:
    """Remove all stored flight/airport rows (used by tests / resets)."""
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM flights")
        conn.execute("DELETE FROM airports")


def export_summary_json(summary: dict, name: str) -> Path:
    """Save an analytics summary dict under ``data/processed/``."""
    from .utils import save_json, timestamp_for_filename

    path = config.DATA_PROCESSED_DIR / f"{name}_{timestamp_for_filename()}.json"
    return save_json(summary, path)
