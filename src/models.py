"""Pydantic validation models for AviationStack API responses.

These models mirror the documented structure of the ``/v1/flights`` endpoint.
Fields that the API commonly returns as ``null`` are Optional, and numeric
fields carry light constraints so bad values are caught during validation
instead of corrupting the dataset later.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Statuses documented by AviationStack.
VALID_FLIGHT_STATUSES = {
    "scheduled",
    "active",
    "landed",
    "cancelled",
    "incident",
    "diverted",
}


class AirportPointInfo(BaseModel):
    """Departure or arrival block inside a flight record."""

    model_config = ConfigDict(extra="ignore")

    airport: Optional[str] = Field(default=None, max_length=200)
    timezone: Optional[str] = Field(default=None, max_length=60)
    iata: Optional[str] = Field(default=None, max_length=4)
    icao: Optional[str] = Field(default=None, max_length=4)
    terminal: Optional[str] = Field(default=None, max_length=10)
    gate: Optional[str] = Field(default=None, max_length=10)
    baggage: Optional[str] = Field(default=None, max_length=10)
    delay: Optional[float] = Field(default=None, ge=0)
    scheduled: Optional[str] = None
    estimated: Optional[str] = None
    actual: Optional[str] = None
    estimated_runway: Optional[str] = None
    actual_runway: Optional[str] = None

    @field_validator("iata", "icao", mode="before")
    @classmethod
    def _upper_code(cls, value: Any) -> Any:
        return value.strip().upper() if isinstance(value, str) else value


class AirlineInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = Field(default=None, max_length=120)
    iata: Optional[str] = Field(default=None, max_length=4)
    icao: Optional[str] = Field(default=None, max_length=4)


class FlightInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    number: Optional[str] = Field(default=None, max_length=10)
    iata: Optional[str] = Field(default=None, max_length=8)
    icao: Optional[str] = Field(default=None, max_length=8)
    codeshared: Optional[dict] = None


class AircraftInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    registration: Optional[str] = Field(default=None, max_length=20)
    iata: Optional[str] = Field(default=None, max_length=10)
    icao: Optional[str] = Field(default=None, max_length=10)
    icao24: Optional[str] = Field(default=None, max_length=10)


class LiveInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    updated: Optional[str] = None
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    altitude: Optional[float] = None
    direction: Optional[float] = Field(default=None, ge=0, le=360)
    speed_horizontal: Optional[float] = Field(default=None, ge=0)
    speed_vertical: Optional[float] = None
    is_ground: Optional[bool] = None


class FlightRecord(BaseModel):
    """One validated flight entry from the AviationStack ``data`` array."""

    model_config = ConfigDict(extra="ignore")

    flight_date: str = Field(min_length=8, max_length=12)
    flight_status: str
    departure: AirportPointInfo
    arrival: AirportPointInfo
    airline: AirlineInfo = Field(default_factory=AirlineInfo)
    flight: FlightInfo = Field(default_factory=FlightInfo)
    aircraft: Optional[AircraftInfo] = None
    live: Optional[LiveInfo] = None

    @field_validator("flight_status")
    @classmethod
    def _check_status(cls, value: str) -> str:
        status = (value or "").strip().lower()
        if status not in VALID_FLIGHT_STATUSES:
            raise ValueError(f"unrecognised flight status {value!r}")
        return status

    @field_validator("flight_date")
    @classmethod
    def _check_date(cls, value: str) -> str:
        from datetime import date

        try:
            date.fromisoformat(value.strip()[:10])
        except ValueError:
            raise ValueError(f"flight_date {value!r} is not ISO formatted")
        return value.strip()[:10]


class PaginationInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    limit: int = 0
    offset: int = 0
    count: int = 0
    total: int = 0


class FlightsResponse(BaseModel):
    """Top-level ``/v1/flights`` payload."""

    model_config = ConfigDict(extra="ignore")

    pagination: PaginationInfo = Field(default_factory=PaginationInfo)
    data: List[FlightRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Batch validation helper
# ---------------------------------------------------------------------------


def validate_flight_records(
    raw_records: List[dict],
) -> Tuple[List[FlightRecord], List[str]]:
    """Validate a list of raw flight dictionaries.

    Returns ``(valid_records, error_messages)`` so callers can keep good
    records while still reporting exactly which entries failed and why.
    """
    valid: List[FlightRecord] = []
    errors: List[str] = []
    for index, raw in enumerate(raw_records):
        try:
            valid.append(FlightRecord.model_validate(raw))
        except Exception as exc:  # pydantic ValidationError
            label = "unknown"
            if isinstance(raw, dict):
                label = (raw.get("flight") or {}).get("iata") or f"row {index}"
            errors.append(f"record {index} ({label}): {exc.errors()[:2]}")
    return valid, errors
