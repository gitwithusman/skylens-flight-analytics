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

# ``utf-8-sig`` strips the byte-order mark that Windows editors (Notepad,
# PowerShell redirection) add; without it the first key in the file is read
# as "\ufeffAVIATIONSTACK_API_KEY" and the API key silently looks unset.
_ENV_ENCODING = "utf-8-sig"
load_dotenv(ENV_FILE, encoding=_ENV_ENCODING)


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable, falling back on bad values."""
    try:
        return int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        return default


def _env_flag(name: str, default: str = "1") -> bool:
    """Interpret an environment variable as an on/off switch."""
    return os.getenv(name, default).strip().lower() not in {"0", "false", "no", ""}

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
ENABLE_WEATHER_LOOKUP = _env_flag("ENABLE_WEATHER_LOOKUP")
# Optional coordinates of a location the user wants weather context for
# (e.g. a home airport). Open-Meteo is queried only when both are set.
WEATHER_LATITUDE = os.getenv("WEATHER_LATITUDE", "").strip()
WEATHER_LONGITUDE = os.getenv("WEATHER_LONGITUDE", "").strip()
WEATHER_LABEL = os.getenv("WEATHER_LABEL", "Monitored location").strip()

# Request behaviour
REQUEST_TIMEOUT = _env_int("REQUEST_TIMEOUT", 20)
DEFAULT_RECORD_LIMIT = _env_int("DEFAULT_RECORD_LIMIT", 100)
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
    load_dotenv(ENV_FILE, override=True, encoding=_ENV_ENCODING)
    AVIATIONSTACK_API_KEY = os.getenv("AVIATIONSTACK_API_KEY", "").strip()
    WEATHER_LATITUDE = os.getenv("WEATHER_LATITUDE", "").strip()
    WEATHER_LONGITUDE = os.getenv("WEATHER_LONGITUDE", "").strip()
    WEATHER_LABEL = os.getenv("WEATHER_LABEL", "Monitored location").strip()
    ENABLE_WEATHER_LOOKUP = _env_flag("ENABLE_WEATHER_LOOKUP")


def _format_env_value(value: object) -> str:
    """Render a value for a .env line, quoting only when necessary."""
    text = "" if value is None else str(value)
    if "\n" in text or "\r" in text:
        raise ValueError("Values stored in .env cannot contain line breaks.")
    if text != text.strip() or any(ch in text for ch in ('#', '"', "'", "=")):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def update_env_file(values: dict) -> None:
    """Create or update ``.env`` with the given key/value pairs.

    Existing keys are replaced in place; unknown keys are appended. Lines
    that are comments or unrelated keys are preserved. A value of ``None``
    clears the key (it is kept in the file with an empty value). The file
    is always written as plain UTF-8 without a byte-order mark.
    """
    lines = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding=_ENV_ENCODING).splitlines()

    remaining = dict(values)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in remaining:
            lines[i] = f"{key}={_format_env_value(remaining.pop(key))}"
    for key, value in remaining.items():
        lines.append(f"{key}={_format_env_value(value)}")
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
