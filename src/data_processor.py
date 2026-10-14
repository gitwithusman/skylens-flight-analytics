"""Pandas transformation and cleaning for validated flight records.

Input:  a list of ``FlightRecord`` Pydantic models (already validated).
Output: tidy DataFrames ready for SQLite loading, analytics and charts.
"""

from __future__ import annotations

from typing import List, Optional

import pandas as pd

from . import config
from .models import FlightRecord
from .utils import get_logger, timestamp_for_filename, utc_now_iso

logger = get_logger()

# Column order used for the flights table / processed dataset.
FLIGHT_COLUMNS = [
    "flight_date",
    "flight_status",
    "flight_iata",
    "flight_icao",
    "flight_number",
    "airline_name",
    "airline_iata",
    "airline_icao",
    "dep_airport",
    "dep_iata",
    "dep_icao",
    "dep_terminal",
    "dep_gate",
    "dep_delay_min",
    "dep_scheduled",
    "dep_estimated",
    "dep_actual",
    "dep_timezone",
    "arr_airport",
    "arr_iata",
    "arr_icao",
    "arr_terminal",
    "arr_gate",
    "arr_baggage",
    "arr_delay_min",
    "arr_scheduled",
    "arr_estimated",
    "arr_actual",
    "arr_timezone",
    "aircraft_registration",
    "aircraft_icao24",
    "is_codeshared",
    "live_latitude",
    "live_longitude",
    "live_altitude",
    "live_speed_kmh",
    "live_is_ground",
    "route",
    "is_delayed",
    "max_delay_min",
    "retrieved_at",
]

# Columns that form the natural uniqueness key for a flight record.
UNIQUE_KEY = ["flight_date", "flight_iata", "dep_iata", "arr_iata"]

SEARCHABLE_TEXT_COLUMNS = [
    "flight_iata",
    "flight_number",
    "airline_name",
    "dep_airport",
    "dep_iata",
    "arr_airport",
    "arr_iata",
    "flight_status",
]


def _record_to_row(record: FlightRecord, retrieved_at: str) -> dict:
    dep = record.departure
    arr = record.arrival
    airline = record.airline
    flight = record.flight
    aircraft = record.aircraft
    live = record.live

    dep_iata = (dep.iata or "").strip() or None
    arr_iata = (arr.iata or "").strip() or None
    dep_delay = dep.delay if dep.delay is not None else None
    arr_delay = arr.delay if arr.delay is not None else None
    delays = [d for d in (dep_delay, arr_delay) if d is not None]

    return {
        "flight_date": record.flight_date,
        "flight_status": record.flight_status,
        "flight_iata": (flight.iata or flight.icao or "").strip() or None,
        "flight_icao": (flight.icao or "").strip() or None,
        "flight_number": (flight.number or "").strip() or None,
        "airline_name": (airline.name or "").strip() or None,
        "airline_iata": (airline.iata or "").strip() or None,
        "airline_icao": (airline.icao or "").strip() or None,
        "dep_airport": (dep.airport or "").strip() or None,
        "dep_iata": dep_iata,
        "dep_icao": (dep.icao or "").strip() or None,
        "dep_terminal": (dep.terminal or "").strip() or None,
        "dep_gate": (dep.gate or "").strip() or None,
        "dep_delay_min": dep_delay,
        "dep_scheduled": dep.scheduled,
        "dep_estimated": dep.estimated,
        "dep_actual": dep.actual,
        "dep_timezone": dep.timezone,
        "arr_airport": (arr.airport or "").strip() or None,
        "arr_iata": arr_iata,
        "arr_icao": (arr.icao or "").strip() or None,
        "arr_terminal": (arr.terminal or "").strip() or None,
        "arr_gate": (arr.gate or "").strip() or None,
        "arr_baggage": (arr.baggage or "").strip() or None,
        "arr_delay_min": arr_delay,
        "arr_scheduled": arr.scheduled,
        "arr_estimated": arr.estimated,
        "arr_actual": arr.actual,
        "arr_timezone": arr.timezone,
        "aircraft_registration": getattr(aircraft, "registration", None),
        "aircraft_icao24": getattr(aircraft, "icao24", None),
        "is_codeshared": bool(flight.codeshared),
        "live_latitude": getattr(live, "latitude", None),
        "live_longitude": getattr(live, "longitude", None),
        "live_altitude": getattr(live, "altitude", None),
        "live_speed_kmh": getattr(live, "speed_horizontal", None),
        "live_is_ground": getattr(live, "is_ground", None),
        "route": f"{dep_iata}-{arr_iata}" if dep_iata and arr_iata else None,
        "is_delayed": bool(delays and max(delays) > 0),
        "max_delay_min": max(delays) if delays else None,
        "retrieved_at": retrieved_at,
    }


def records_to_dataframe(records: List[FlightRecord]) -> pd.DataFrame:
    """Flatten validated records into the canonical flights DataFrame."""
    retrieved_at = utc_now_iso()
    rows = [_record_to_row(rec, retrieved_at) for rec in records]
    df = pd.DataFrame(rows, columns=FLIGHT_COLUMNS)
    if df.empty:
        return df
    return clean_flights(df)


def clean_flights(df: pd.DataFrame) -> pd.DataFrame:
    """Apply consistent cleaning: types, duplicates, date parsing."""
    df = df.copy()

    for col in ("dep_delay_min", "arr_delay_min", "max_delay_min"):
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for col in ("dep_scheduled", "dep_estimated", "dep_actual",
                "arr_scheduled", "arr_estimated", "arr_actual"):
        if col in df:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    if "flight_date" in df:
        df["flight_date"] = df["flight_date"].astype(str).str[:10]
    for col in ("is_codeshared", "is_delayed"):
        if col in df:
            df[col] = df[col].fillna(False).astype(bool)
    if "live_is_ground" in df:
        df["live_is_ground"] = df["live_is_ground"].astype("boolean")

    # Standardise text columns.
    for col in df.columns:
        if df[col].dtype == object and col not in ("retrieved_at",):
            df[col] = df[col].where(df[col].isna(), df[col].astype(str).str.strip())

    # Drop rows that cannot be identified at all.
    key_cols = [c for c in UNIQUE_KEY if c in df]
    if key_cols:
        keep = [c for c in ("dep_iata", "arr_iata") if c in df]
        if keep:
            df = df.dropna(subset=keep, how="all")
        df = df.drop_duplicates(subset=key_cols, keep="last")
    return df.reset_index(drop=True)


def derive_airports(flights_df: pd.DataFrame) -> pd.DataFrame:
    """Build an airports table from the departure/arrival blocks of flights.

    Every row comes straight from the API payload - no external airport list
    is invented. ``sightings`` counts how often each airport appeared.
    """
    if flights_df.empty:
        return pd.DataFrame(
            columns=["airport_name", "iata", "icao", "timezone",
                     "departures", "arrivals", "sightings"]
        )

    dep = flights_df[["dep_airport", "dep_iata", "dep_icao", "dep_timezone"]].rename(
        columns={"dep_airport": "airport_name", "dep_iata": "iata",
                 "dep_icao": "icao", "dep_timezone": "timezone"}
    )
    dep["departures"] = 1
    dep["arrivals"] = 0

    arr = flights_df[["arr_airport", "arr_iata", "arr_icao", "arr_timezone"]].rename(
        columns={"arr_airport": "airport_name", "arr_iata": "iata",
                 "arr_icao": "icao", "arr_timezone": "timezone"}
    )
    arr["departures"] = 0
    arr["arrivals"] = 1

    combined = pd.concat([dep, arr], ignore_index=True)
    combined = combined.dropna(subset=["iata"])
    if combined.empty:
        return pd.DataFrame(
            columns=["airport_name", "iata", "icao", "timezone",
                     "departures", "arrivals", "sightings"]
        )

    grouped = (
        combined.groupby("iata", as_index=False)
        .agg(
            airport_name=("airport_name", "first"),
            icao=("icao", "first"),
            timezone=("timezone", "first"),
            departures=("departures", "sum"),
            arrivals=("arrivals", "sum"),
        )
    )
    grouped["sightings"] = grouped["departures"] + grouped["arrivals"]
    return grouped.sort_values("sightings", ascending=False).reset_index(drop=True)


def quality_report(df: pd.DataFrame) -> dict:
    """Basic data-quality metrics shown by both applications."""
    if df.empty:
        return {
            "rows": 0,
            "columns": 0,
            "missing_values": {},
            "duplicate_rows": 0,
            "unique_flights": 0,
            "delay_data_available": False,
        }
    return {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "missing_values": {c: int(v) for c, v in df.isna().sum().items() if v},
        "duplicate_rows": int(df.duplicated(subset=UNIQUE_KEY).sum()),
        "unique_flights": int(df["flight_iata"].nunique(dropna=True)),
        "delay_data_available": bool(df["max_delay_min"].notna().any()),
    }


def save_processed(df: pd.DataFrame, name: str = "flights_processed") -> Optional[str]:
    """Persist the processed dataset to ``data/processed/`` as CSV."""
    if df.empty:
        return None
    path = config.DATA_PROCESSED_DIR / f"{name}_{timestamp_for_filename()}.csv"
    df.to_csv(path, index=False)
    latest = config.DATA_PROCESSED_DIR / f"{name}_latest.csv"
    df.to_csv(latest, index=False)
    logger.info("Processed dataset saved to %s", path)
    return str(path)


def load_latest_processed(name: str = "flights_processed") -> pd.DataFrame:
    """Load the most recent processed CSV if it exists."""
    latest = config.DATA_PROCESSED_DIR / f"{name}_latest.csv"
    if not latest.exists():
        return pd.DataFrame(columns=FLIGHT_COLUMNS)
    df = pd.read_csv(latest, low_memory=False)
    return clean_flights(df) if not df.empty else df
