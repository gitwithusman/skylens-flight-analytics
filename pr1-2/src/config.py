"""Configuration and environment-variable loading.

All credentials come from environment variables or a ``.env`` file at the
project root. No secret is ever hard-coded in this project.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_RAW_DIR = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
DATABASE_DIR = PROJECT_ROOT / "database"
DATABASE_PATH = DATABASE_DIR / "flight_airport.db"
VISUALIZATIONS_DIR = PROJECT_ROOT / "visualizations"
ASSETS_DIR = PROJECT_ROOT / "assets"
LOG_DIR = PROJECT_ROOT / "outputs" / "logs"
ENV_FILE = PROJECT_ROOT / ".env"

for _directory in (
    DATA_RAW_DIR,
    DATA_PROCESSED_DIR,
    DATABASE_DIR,
    VISUALIZATIONS_DIR,
    LOG_DIR,
):
    _directory.mkdir(parents=True, exist_ok=True)

load_dotenv(ENV_FILE)

# ---------------------------------------------------------------------------
# API settings
# ---------------------------------------------------------------------------
# AviationStack - https://aviationstack.com (free tier: /v1/flights endpoint).
AVIATIONSTACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY", "").strip()
# NOTE: the free AviationStack plan is HTTP-only; paid plans may switch
# this to https:// in .env.
AVIATIONSTACK_BASE_URL = os.getenv(
    "AVIATIONSTACK_BASE_URL", "http://api.aviationstack.com/v1"
).rstrip("/")

# Open-Meteo - free weather API, no key required. Used only for optional
# informational weather lookups; it is never used to attribute delays.
OPENMETEO_BASE_URL = os.getenv(
    "OPENMETEO_BASE_URL", "https://api.open-meteo.com/v1"
).rstrip("/")
ENABLE_WEATHER_LOOKUP = os.getenv("ENABLE_WEATHER_LOOKUP", "1") not in {
    "0",
    "false",
    "no",
}
# Optional coordinates of a location the user wants weather context for
# (e.g. a home airport). Open-Meteo is queried only when both are set.
WEATHER_LATITUDE = os.getenv("WEATHER_LATITUDE", "").strip()
WEATHER_LONGITUDE = os.getenv("WEATHER_LONGITUDE", "").strip()
WEATHER_LABEL = os.getenv("WEATHER_LABEL", "Monitored location").strip()

# Request behaviour
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "20"))
DEFAULT_RECORD_LIMIT = int(os.getenv("DEFAULT_RECORD_LIMIT", "100"))
MAX_RECORD_LIMIT = 1000  # aviationstack caps the "limit" parameter


def api_key_configured() -> bool:
    """Return True when an AviationStack access key is present."""
    return bool(AVIATIONSTACK_API_KEY)


def masked_api_key() -> str:
    """Return the API key masked for display (never shows the full secret)."""
    key = AVIATIONSTACK_API_KEY
    if not key:
        return "(not set)"
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"


def reload_environment() -> None:
    """Reload .env values - used after the Settings page updates the file."""
    global AVIATIONSTACK_API_KEY, WEATHER_LATITUDE, WEATHER_LONGITUDE
    global WEATHER_LABEL, ENABLE_WEATHER_LOOKUP
    load_dotenv(ENV_FILE, override=True)
    AVIATIONSTACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY", "").strip()
    WEATHER_LATITUDE = os.getenv("WEATHER_LATITUDE", "").strip()
    WEATHER_LONGITUDE = os.getenv("WEATHER_LONGITUDE", "").strip()
    WEATHER_LABEL = os.getenv("WEATHER_LABEL", "Monitored location").strip()
    ENABLE_WEATHER_LOOKUP = os.getenv("ENABLE_WEATHER_LOOKUP", "1") not in {
        "0", "false", "no",
    }


def update_env_file(values: dict) -> None:
    """Create or update ``.env`` with the given key/value pairs.

    Existing keys are replaced in place; unknown keys are appended. Lines
    that are comments or unrelated keys are preserved.
    """
    lines = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()

    remaining = dict(values)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"
    for key, value in remaining.items():
        lines.append(f"{key}={value}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def data_source_status() -> dict:
    """Summarise configuration status for display in both front-ends."""
    return {
        "provider": "AviationStack",
        "api_key_configured": api_key_configured(),
        "api_key_display": masked_api_key(),
        "base_url": AVIATIONSTACK_BASE_URL,
        "weather_provider": "Open-Meteo" if ENABLE_WEATHER_LOOKUP else "disabled",
        "request_timeout": REQUEST_TIMEOUT,
        "default_limit": DEFAULT_RECORD_LIMIT,
        "database_path": str(DATABASE_PATH),
    }
