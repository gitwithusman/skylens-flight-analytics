"""HTTP client for the AviationStack API (and optional Open-Meteo weather).

AviationStack docs: https://aviationstack.com/documentation
Free plan supports the real-time ``/v1/flights`` endpoint with ``access_key``
authentication. Lookup endpoints such as ``/v1/airports`` require a paid plan,
so the application derives airport records from flight data instead.

Open-Meteo (https://open-meteo.com) is a free, key-less weather API used only
for informational lookups at airport coordinates; it is never used to claim a
delay was caused by weather.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import requests

from . import config
from .utils import (
    APIError,
    AuthenticationError,
    RateLimitError,
    get_logger,
    timestamp_for_filename,
)

logger = get_logger()

# Flight statuses the API accepts for server-side filtering.
FILTERABLE_STATUSES = (
    "scheduled",
    "active",
    "landed",
    "cancelled",
    "incident",
    "diverted",
)


def _handle_error_payload(payload: dict) -> None:
    """Raise a specific exception for AviationStack ``{"error": ...}`` bodies."""
    error = payload.get("error") if isinstance(payload, dict) else None
    if not error:
        return
    if not isinstance(error, dict):  # some gateways return a bare string
        error = {"message": str(error)}
    code = str(error.get("code", "unknown_error"))
    message = str(error.get("message", "Unknown API error"))
    logger.warning("AviationStack error %s: %s", code, message)
    if code in {
        "missing_access_key",
        "invalid_access_key",
        "not_authenticated",
        "invalid_api_key",
        "101",
    }:
        raise AuthenticationError(
            f"API authentication failed ({code}). Check AVIATIONSTACK_API_KEY in .env."
        )
    if code in {"usage_limit_reached", "rate_limit_reached", "104"} or "limit" in code:
        raise RateLimitError(
            f"API usage limit reached ({code}). Free plan allows ~100 requests/month."
        )
    if code in {
        "function_access_restricted",
        "https_access_restricted",
        "not_found",
    }:
        raise APIError(f"Endpoint not available on this plan ({code}): {message}")
    raise APIError(f"AviationStack error {code}: {message}")


def _request(endpoint: str, params: Optional[Dict[str, Any]] = None) -> dict:
    """Perform a GET request against the AviationStack API."""
    if not config.api_key_configured():
        raise AuthenticationError(
            "No AVIATIONSTACK_API_KEY configured. Copy .env.example to .env "
            "and add your key from https://aviationstack.com"
        )

    url = f"{config.AVIATIONSTACK_BASE_URL}/{endpoint.lstrip('/')}"
    query = {"access_key": config.AVIATIONSTACK_API_KEY}
    query.update({k: v for k, v in (params or {}).items() if v not in (None, "")})

    try:
        response = requests.get(url, params=query, timeout=config.REQUEST_TIMEOUT)
    except requests.exceptions.Timeout:
        raise APIError(
            f"Request to {url} timed out after {config.REQUEST_TIMEOUT}s."
        )
    except requests.exceptions.ConnectionError:
        raise APIError("Could not reach aviationstack.com - check your connection.")
    except requests.exceptions.RequestException as exc:
        raise APIError(f"HTTP request failed: {exc}")

    # AviationStack explains failures in a JSON body even on 4xx responses
    # (e.g. 403 with {"error": {"code": ..., "message": ...}}). Read it first
    # so the user sees the real reason instead of a bare status code.
    try:
        payload = response.json()
    except (json.JSONDecodeError, ValueError):
        payload = None
    _handle_error_payload(payload)

    if response.status_code == 401:
        raise AuthenticationError("API returned 401 - the access key is invalid.")
    if response.status_code == 429:
        raise RateLimitError("API returned 429 - rate limit reached, try later.")
    if response.status_code >= 400:
        raise APIError(f"API returned HTTP {response.status_code}.")
    if payload is None:
        raise APIError("API response was not valid JSON.")
    if not isinstance(payload, dict) or "data" not in payload:
        raise APIError("Unexpected API response structure (missing 'data').")
    return payload


def fetch_flights(
    limit: int = config.DEFAULT_RECORD_LIMIT,
    offset: int = 0,
    flight_status: Optional[str] = None,
    dep_iata: Optional[str] = None,
    arr_iata: Optional[str] = None,
    airline_name: Optional[str] = None,
    flight_number: Optional[str] = None,
    save_raw: bool = True,
) -> dict:
    """Retrieve flight records from ``/v1/flights``.

    Returns the raw decoded payload. ``save_raw`` stores a copy under
    ``data/raw/`` before any transformation takes place.
    """
    params: Dict[str, Any] = {
        "limit": min(max(1, int(limit)), config.MAX_RECORD_LIMIT),
        "offset": max(0, int(offset)),
    }
    if flight_status and flight_status.lower() in FILTERABLE_STATUSES:
        params["flight_status"] = flight_status.lower()
    if dep_iata:
        params["dep_iata"] = dep_iata.strip().upper()
    if arr_iata:
        params["arr_iata"] = arr_iata.strip().upper()
    if airline_name:
        params["airline_name"] = airline_name.strip()
    if flight_number:
        params["flight_number"] = flight_number.strip()

    logger.info("Requesting flights (limit=%s offset=%s)", params["limit"], offset)
    payload = _request("flights", params)

    if save_raw:
        from .utils import save_json

        path = config.DATA_RAW_DIR / f"flights_raw_{timestamp_for_filename()}.json"
        save_json(payload, path)
        logger.info("Raw response saved to %s", path)
    return payload


def fetch_airports_endpoint(limit: int = 100) -> dict:
    """Try the ``/v1/airports`` lookup endpoint.

    AviationStack restricts this endpoint to paid plans; when unavailable the
    raised APIError is handled by the caller, which falls back to airports
    derived from flight records.
    """
    return _request("airports", {"limit": min(max(1, int(limit)), 1000)})


def fetch_weather(latitude: float, longitude: float) -> Optional[dict]:
    """Fetch current weather from Open-Meteo for display purposes.

    Returns ``None`` on any failure - weather is informational only and must
    never block the rest of the application.
    """
    if not config.ENABLE_WEATHER_LOOKUP:
        return None
    try:
        response = requests.get(
            f"{config.OPENMETEO_BASE_URL}/forecast",
            params={
                "latitude": latitude,
                "longitude": longitude,
                "current": "temperature_2m,weather_code,wind_speed_10m",
            },
            timeout=min(10, config.REQUEST_TIMEOUT),
        )
        if response.status_code != 200:
            return None
        current = response.json().get("current") or {}
        return {
            "temperature_c": current.get("temperature_2m"),
            "weather_code": current.get("weather_code"),
            "wind_speed_kmh": current.get("wind_speed_10m"),
        }
    except requests.exceptions.RequestException:
        return None


# WMO weather interpretation codes (subset relevant to flight disruption).
WMO_SEVERE_CODES = {45, 48, 51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 71, 73, 75,
                    77, 80, 81, 82, 85, 86, 95, 96, 99}


def weather_summary(weather: Optional[dict]) -> str:
    """Human-readable one-line weather description."""
    if not weather:
        return "Weather unavailable"
    temp = weather.get("temperature_c")
    wind = weather.get("wind_speed_kmh")
    parts = []
    if temp is not None:
        parts.append(f"{temp:.0f}°C")
    if wind is not None:
        parts.append(f"wind {wind:.0f} km/h")
    code = weather.get("weather_code")
    if code in WMO_SEVERE_CODES:
        parts.append("adverse conditions reported")
    return ", ".join(parts) if parts else "Weather unavailable"
