"""Statistical analysis and insights over the processed flight dataset.

Every function accepts the flights DataFrame (from the processor or SQLite)
and returns plain Python structures so both the terminal app and the GUI can
present the same results. Analyses that need a field which is missing simply
report that limitation instead of inventing numbers.
"""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

STATUS_LABELS = {
    "scheduled": "Scheduled",
    "active": "Active",
    "landed": "Landed",
    "cancelled": "Cancelled",
    "incident": "Incident",
    "diverted": "Diverted",
}


def dataset_overview(df: pd.DataFrame) -> Dict:
    """High-level dataset description."""
    if df.empty:
        return {
            "rows": 0, "columns": 0, "column_names": [],
            "missing_total": 0, "missing_by_column": {},
            "duplicate_rows": 0, "date_range": None,
        }
    return {
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "column_names": list(df.columns),
        "missing_total": int(df.isna().sum().sum()),
        "missing_by_column": {
            c: int(v) for c, v in df.isna().sum().items() if v
        },
        "duplicate_rows": int(df.duplicated().sum()),
        "date_range": (
            (str(df["flight_date"].min()), str(df["flight_date"].max()))
            if "flight_date" in df
            else None
        ),
    }


def status_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Counts and percentages per flight status."""
    if df.empty or "flight_status" not in df:
        return pd.DataFrame(columns=["flight_status", "flights", "share_pct"])
    counts = df["flight_status"].value_counts(dropna=False)
    total = counts.sum() or 1
    result = counts.rename_axis("flight_status").reset_index(name="flights")
    result["flight_status"] = result["flight_status"].astype(str)
    result["share_pct"] = (result["flights"] / total * 100).round(1)
    return result


def top_airlines(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Most active airlines by number of stored flights."""
    if df.empty or "airline_name" not in df:
        return pd.DataFrame(columns=["airline", "flights"])
    series = (
        df["airline_name"].fillna(df.get("airline_iata"))
        if "airline_iata" in df
        else df["airline_name"]
    )
    counts = series.dropna().value_counts().head(n)
    return counts.rename_axis("airline").reset_index(name="flights")


def top_airports(df: pd.DataFrame, role: str = "dep", n: int = 10) -> pd.DataFrame:
    """Busiest departure (``role='dep'``) or arrival airports."""
    col = {"dep": "dep_airport", "arr": "arr_airport"}.get(role, "dep_airport")
    code = {"dep": "dep_iata", "arr": "arr_iata"}.get(role, "dep_iata")
    if df.empty or col not in df:
        return pd.DataFrame(columns=["airport", "iata", "flights"])
    sub = df[[col, code]].dropna(subset=[col])
    counts = sub.groupby([col, code]).size().nlargest(n)
    result = counts.rename("flights").reset_index()
    result.columns = ["airport", "iata", "flights"]
    return result


def top_routes(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Most frequent departure->arrival routes."""
    if df.empty or "route" not in df:
        return pd.DataFrame(columns=["route", "flights"])
    counts = df["route"].dropna().value_counts().head(n)
    return counts.rename_axis("route").reset_index(name="flights")


def delay_statistics(df: pd.DataFrame) -> Dict:
    """Delay metrics - only reported when real delay fields exist."""
    if df.empty or "max_delay_min" not in df:
        return {
            "available": False,
            "reason": "The dataset contains no delay fields.",
        }
    delays = df["max_delay_min"].dropna()
    if delays.empty:
        return {
            "available": False,
            "reason": "The API did not return delay values for these flights.",
        }
    delayed = delays[delays > 0]
    return {
        "available": True,
        "flights_with_delay_data": int(delays.count()),
        "delayed_flights": int(len(delayed)),
        "delayed_share_pct": round(len(delayed) / len(df) * 100, 1),
        "avg_delay_min": round(float(delays.mean()), 1),
        "median_delay_min": round(float(delays.median()), 1),
        "max_delay_min": float(delays.max()),
    }


def departure_hour_distribution(df: pd.DataFrame) -> pd.DataFrame:
    """Flights per scheduled-departure hour (requires parseable times)."""
    if df.empty or "dep_scheduled" not in df:
        return pd.DataFrame(columns=["hour", "flights"])
    hours = pd.to_datetime(df["dep_scheduled"], errors="coerce", utc=True).dt.hour
    counts = hours.dropna().astype(int).value_counts().sort_index()
    return counts.rename_axis("hour").reset_index(name="flights")


def codeshare_share(df: pd.DataFrame) -> Dict:
    if df.empty or "is_codeshared" not in df:
        return {"codeshared": 0, "share_pct": 0.0}
    count = int(df["is_codeshared"].sum())
    return {"codeshared": count, "share_pct": round(count / len(df) * 100, 1)}


def unique_value_counts(df: pd.DataFrame) -> Dict[str, int]:
    """Distinct counts of the most interesting categorical fields."""
    fields = {
        "airlines": "airline_name",
        "departure_airports": "dep_iata",
        "arrival_airports": "arr_iata",
        "routes": "route",
        "flight_numbers": "flight_iata",
    }
    return {
        label: int(df[col].nunique(dropna=True)) if col in df else 0
        for label, col in fields.items()
    }


def numeric_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Descriptive statistics for the genuinely numeric columns."""
    numeric = [
        c
        for c in ("dep_delay_min", "arr_delay_min", "max_delay_min",
                  "live_altitude", "live_speed_kmh")
        if c in df and df[c].notna().any()
    ]
    if df.empty or not numeric:
        return pd.DataFrame(
            columns=["column", "count", "mean", "std", "min", "median", "max"]
        )
    desc = df[numeric].describe().T
    desc["median"] = df[numeric].median()
    out = desc[["count", "mean", "std", "min", "median", "max"]].round(2)
    return out.rename_axis("column").reset_index()


def full_summary(df: pd.DataFrame, airports_df: Optional[pd.DataFrame] = None) -> Dict:
    """Aggregate everything into one dictionary for reporting/export."""
    summary = {
        "overview": dataset_overview(df),
        "unique_counts": unique_value_counts(df),
        "status_distribution": status_distribution(df).to_dict("records"),
        "top_airlines": top_airlines(df).to_dict("records"),
        "top_departure_airports": top_airports(df, "dep").to_dict("records"),
        "top_arrival_airports": top_airports(df, "arr").to_dict("records"),
        "top_routes": top_routes(df).to_dict("records"),
        "delays": delay_statistics(df),
        "codeshares": codeshare_share(df),
        "departure_hours": departure_hour_distribution(df).to_dict("records"),
    }
    if airports_df is not None:
        summary["airport_records"] = int(len(airports_df))
    return summary


# ---------------------------------------------------------------------------
# Status classification used by the GUI status bar
# ---------------------------------------------------------------------------


def classify_condition(row) -> Dict[str, str]:
    """Map one stored flight row to a display condition.

    Categories: On Time, Delayed, Cancelled, Weather Delay, Weather Alert,
    Status Unknown. Weather-related categories are only returned when the
    data source explicitly confirms weather involvement (AviationStack's
    free tier does not provide delay causes, so these normally stay unused).
    """
    status = str(row.get("flight_status", "") or "").lower()
    delay = row.get("max_delay_min")
    delay = float(delay) if pd.notna(delay) else 0.0
    weather_confirmed = bool(row.get("weather_confirmed", False))

    if status == "cancelled":
        return {"label": "Cancelled", "color": "#d9534f"}
    if delay > 0:
        if weather_confirmed:
            return {"label": f"Weather Delay {int(delay)} min", "color": "#c46bd8"}
        return {"label": f"Delayed {int(delay)} min", "color": "#e8a33d"}
    if weather_confirmed:
        return {"label": "Weather Alert", "color": "#c46bd8"}
    if status in {"incident", "diverted"}:
        return {"label": STATUS_LABELS.get(status, "Alert"), "color": "#f0ad4e"}
    if status in {"scheduled", "active"}:
        return {"label": "On Time", "color": "#4caf7d"}
    if status == "landed":
        return {"label": "Landed", "color": "#5bc0de"}
    return {"label": "Status Unknown", "color": "#8a8f98"}


# Raw-status colors for table cells (keyed by the API's own status values).
STATUS_VALUE_COLORS = {
    "scheduled": "#4caf7d",
    "active": "#4caf7d",
    "landed": "#5bc0de",
    "cancelled": "#d9534f",
    "incident": "#f0ad4e",
    "diverted": "#f0ad4e",
}

# Distinct colors for every category shown in the GUI status bar.
STATUS_BAR_COLORS = {
    "On Time": "#4caf7d",
    "Delayed": "#e8a33d",
    "Cancelled": "#d9534f",
    "Weather Alert": "#c46bd8",
    "Weather Delay": "#c46bd8",
    "Status Unknown": "#8a8f98",
    "Landed": "#5bc0de",
    "Incident": "#f0ad4e",
    "Diverted": "#f0ad4e",
}
