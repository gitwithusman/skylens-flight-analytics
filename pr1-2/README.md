# Flight and Airport Analytics

A Python application for retrieving, exploring and analysing real flight and
airport information. It provides **two fully working front-ends** over the
same shared code and SQLite database:

- **Terminal application** — `python main_task/main.py`
- **Desktop GUI (PySide6)** — `python main_task/gui_main.py`

Pipeline: AviationStack REST API → Pydantic validation → pandas
transformation → SQLite storage → analytics & Matplotlib/Seaborn charts.

---

## 1. Quick start

```bash
# 1. Install dependencies (Python 3.10+)
pip install -r requirements.txt

# 2. Configure the API key
copy .env.example .env        # Windows
# cp .env.example .env        # macOS / Linux
#   then edit .env and set:   AVIATIONSTACK_API_KEY=<your key>

# 3a. Terminal application
python main_task/main.py

# 3b. Desktop GUI
python main_task/gui_main.py

# 4. Run the test suite
python -m pytest tests/ -v
```

Both applications must be launched **from the project root folder**.

---

## 2. Data source — AviationStack

**Chosen API:** [AviationStack](https://aviationstack.com) (`/v1/flights`)

Why it was chosen:

- Free tier with a simple `access_key` query parameter — no OAuth.
- Each flight object embeds **departure and arrival airport** details
  (name, IATA/ICAO, terminal, gate, timezone, delay), **airline** info,
  flight status, schedule/actual timestamps and optional live position —
  enough for genuine analytics without extra paid calls.
- Airport records are *derived* from those embedded airport blocks, so the
  Airports page always shows real data from the same source. The paid
  `/v1/airports` directory endpoint is not assumed to be available.

Free-tier limitations handled by the app:

- ~100 requests/month → results are persisted in SQLite between runs.
- No historical data and no delay *causes* → the app never attributes a
  delay to weather unless the source confirms it.
- Lookup endpoints (`/airports`, `/routes`) may return
  `function_access_restricted` on the free plan → handled gracefully.

**Optional weather context:** [Open-Meteo](https://open-meteo.com) (free, no
key) can display current weather for a location you configure in Settings
(`WEATHER_LATITUDE` / `WEATHER_LONGITUDE` / `WEATHER_LABEL`). It is purely
informational.

### Getting an API key

1. Register free at https://aviationstack.com and copy your access key.
2. Create `.env` from `.env.example` and set `AVIATIONSTACK_API_KEY`.
3. Alternatively paste it in the GUI **Settings** page (it is stored in
   `.env` and never displayed in full).

---

## 3. What the application does

### Terminal app (`main_task/main.py`)

Numbered menu covering: overview, data retrieval with optional API filters
(status, dep/arr IATA, airline, flight number, limit), flight/airport
record viewers, search & filters, statistics, full exploratory analysis
(missing values, duplicates, top airlines/airports/routes, departure-hour
patterns, numeric summary), chart generation (saved as PNG), database
inspection, CSV/JSON export and configuration status. All input is
validated and all errors produce readable messages.

### Desktop app (`main_task/gui_main.py`)

| Page            | Contents |
|-----------------|----------|
| Dashboard       | Live metric cards (flights, airports, airlines, delayed, routes, last refresh), empty state with retrieve action, quick navigation |
| Flights         | Sortable/searchable table with status filter and "delayed only" toggle |
| Airports        | Searchable airport table derived from real flight data |
| Search          | Field-aware search + status/route/delay filters, clear button, match counts |
| Analytics       | Metric cards + six live analysis tables |
| Visualizations  | Seven chart types, regenerate + save PNG |
| Data Management | Retrieval with filters, DB status, export to CSV/JSON |
| Settings        | Masked API-key handling, weather lookup options |
| About           | Version, description, credits |

A **flight-conditions status bar** at the bottom shows colour-coded counts
(On Time, Delayed, Cancelled, Weather Alert, Weather Delay, Landed, Status
Unknown) computed from actual stored rows, refreshed after every retrieval.
Network work runs on background threads so the UI stays responsive.

---

## 4. Project structure

```
Flight_Airport_Analytics/
├── main_task/
│   ├── main.py              # terminal entry point
│   └── gui_main.py          # PySide6 desktop entry point
├── src/
│   ├── __init__.py
│   ├── config.py            # paths, .env loading, settings
│   ├── api_client.py        # AviationStack + Open-Meteo HTTP clients
│   ├── models.py            # Pydantic response validation
│   ├── data_processor.py    # pandas cleaning / derived columns / airports
│   ├── database.py          # SQLite schema, upserts, queries, export
│   ├── analytics.py         # statistics & insights
│   ├── visualizations.py    # matplotlib/seaborn chart registry
│   ├── service.py           # shared refresh orchestration
│   └── utils.py             # logging, error types, helpers
├── data/
│   ├── raw/                 # untouched API responses (JSON)
│   └── processed/           # cleaned CSV datasets & exports
├── database/
│   └── flight_airport.db    # SQLite database (created on first run)
├── visualizations/          # generated PNG charts
├── assets/                  # icons / images
├── tests/                   # pytest suite (no network required)
├── outputs/logs/            # application.log
├── .env.example             # configuration template (no secrets)
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 5. Data flow and deduplication

1. `api_client.fetch_flights()` calls `/v1/flights` with the configured key
   and filters; the raw JSON is archived under `data/raw/`.
2. `models.validate_flight_records()` validates every record with Pydantic
   (status vocabulary, ISO dates, numeric ranges, nested structures);
   rejected rows are reported, not silently fixed.
3. `data_processor.records_to_dataframe()` flattens records, parses
   timestamps, builds derived columns (`route`, `is_delayed`,
   `max_delay_min`) and removes duplicates.
4. `database.insert_flights()` upserts rows. The natural uniqueness key is
   `(flight_date, flight_iata, dep_iata, arr_iata)` — re-retrieving the
   same flights updates them instead of duplicating them.
5. `derive_airports()` aggregates the embedded departure/arrival airport
   blocks into an `airports` table with sighting counts.
6. Both apps then read through `database.fetch_flights()` /
   `fetch_airports()` and share `analytics.py` / `visualizations.py`.

Every refresh is recorded in the `refresh_log` table (timestamp, fetched /
valid / stored counts, status, message) and surfaced on the Dashboard and
Data Management pages.

---

## 6. Configuration reference (`.env`)

| Variable | Purpose | Required |
|---|---|---|
| `AVIATIONSTACK_API_KEY` | your AviationStack access key | yes, for retrieval |
| `AVIATIONSTACK_BASE_URL` | API base URL — free plan **requires `http://`**, paid plans may use `https://` | no |
| `REQUEST_TIMEOUT` | HTTP timeout in seconds | no (20) |
| `DEFAULT_RECORD_LIMIT` | rows fetched per refresh | no (100) |
| `ENABLE_WEATHER_LOOKUP` | `1`/`0` — show weather chip in GUI | no |
| `WEATHER_LATITUDE` / `WEATHER_LONGITUDE` | coordinates for weather lookup | no |
| `WEATHER_LABEL` | display name of the monitored location | no |

---

## 7. Tests

```bash
python -m pytest tests/ -v
```

The suite covers Pydantic validation (bad status/date/types, null sections,
batch error reporting), pandas processing (flattening, derived columns,
dedup, airport derivation, quality report), the SQLite layer (insert,
dedup-on-refresh, filters, exports, refresh log) and analytics/chart
builders (including empty-dataset behaviour). Tests use a bundled
AviationStack-shaped fixture — **no network or API key is needed**.

---

## 8. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| "No AVIATIONSTACK_API_KEY configured" | Create `.env` from `.env.example` and add your key, or use GUI → Settings. |
| "API usage limit reached" | Free tier ≈100 requests/month; wait for reset or upgrade. Stored data keeps working. |
| "Endpoint not available on this plan" | You hit a paid endpoint; the app only needs `/v1/flights`. |
| "https_access_restricted" error | Free plan is HTTP-only — keep `AVIATIONSTACK_BASE_URL=http://...` in `.env`. |
| Charts look empty | No records stored yet — retrieve data first. |
| GUI does not start | `pip install PySide6`, then run from the project root. |
| Old data shown after a failed refresh | By design — the last refresh status is shown in Dashboard / Data pages. |
