"""Application service layer shared by the terminal app and the GUI.

This module wires the full data flow together:

    API request -> Pydantic validation -> Pandas transformation
    -> SQLite loading -> refresh log

Keeping it in one place guarantees both applications perform exactly the
same steps when the user asks for fresh data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import pandas as pd

from . import api_client, database, data_processor
from .models import validate_flight_records
from .utils import AppError, get_logger

logger = get_logger()


@dataclass
class RefreshResult:
    """Outcome of a retrieve-and-store cycle."""

    success: bool
    message: str
    fetched: int = 0
    valid: int = 0
    invalid: int = 0
    stored: int = 0
    airports_stored: int = 0
    validation_errors: List[str] = field(default_factory=list)
    processed_file: Optional[str] = None


def refresh_data(
    limit: int = 100,
    flight_status: Optional[str] = None,
    dep_iata: Optional[str] = None,
    arr_iata: Optional[str] = None,
    airline_name: Optional[str] = None,
    flight_number: Optional[str] = None,
    db_path=None,
) -> RefreshResult:
    """Retrieve flights from the API, validate, transform and store them.

    Raises ``AppError`` subclasses for hard failures (no key, network down,
    quota exhausted); validation problems degrade gracefully.
    """
    payload = api_client.fetch_flights(
        limit=limit,
        flight_status=flight_status,
        dep_iata=dep_iata,
        arr_iata=arr_iata,
        airline_name=airline_name,
        flight_number=flight_number,
    )
    raw_records = payload.get("data") or []
    fetched = len(raw_records)

    if fetched == 0:
        database.log_refresh("aviationstack/flights", 0, 0, 0,
                             "empty", "API returned no records", db_path)
        return RefreshResult(
            success=True,
            fetched=0,
            message="The API returned zero flights for the chosen filters.",
        )

    valid_records, errors = validate_flight_records(raw_records)
    flights_df = data_processor.records_to_dataframe(valid_records)
    airports_df = data_processor.derive_airports(flights_df)

    stored = database.insert_flights(flights_df, db_path)
    airports_stored = database.insert_airports(airports_df, db_path)
    processed_file = data_processor.save_processed(flights_df)

    status = "success" if not errors else "partial"
    message = (
        f"Stored {stored} flight records ({len(errors)} rejected by validation)."
        if errors
        else f"Stored {stored} flight records."
    )
    database.log_refresh(
        "aviationstack/flights", fetched, len(valid_records), stored,
        status, message, db_path,
    )
    logger.info(
        "Refresh complete: fetched=%d valid=%d stored=%d airports=%d",
        fetched, len(valid_records), stored, airports_stored,
    )
    return RefreshResult(
        success=True,
        message=message,
        fetched=fetched,
        valid=len(valid_records),
        invalid=len(errors),
        stored=stored,
        airports_stored=airports_stored,
        validation_errors=errors,
        processed_file=processed_file,
    )


def load_stored_flights(**filters) -> pd.DataFrame:
    """Read stored flights through the same path as the database module."""
    return database.fetch_flights(**filters)


def dataset_available(db_path=None) -> bool:
    """True when the database already contains usable flight records."""
    try:
        return database.count_rows("flights", db_path) > 0
    except AppError:
        return False
