"""
config.py
=========
Central place for every configurable value in the project.

Why a dedicated config module?
- Keeps secrets (API key) out of code via environment variables (.env).
- Gives every other module a single, predictable import (`from src import config`)
  instead of scattering `os.getenv()` calls everywhere.
- Makes the project easy to re-target at a different city/area later by only
  touching this file or the .env, never the logic in google_places.py.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load environment variables from a .env file (if present) into os.environ.
# In production (e.g. CI, Docker, cloud run) you would instead set real
# environment variables and skip .env entirely — load_dotenv() is a no-op
# if no .env file exists, so this is safe either way.
# ---------------------------------------------------------------------------
load_dotenv()

# ---------------------------------------------------------------------------
# API key — REQUIRED. We fail fast with a clear message rather than letting
# a cryptic 403 surface later from inside an HTTP call.
# ---------------------------------------------------------------------------
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()

if not GOOGLE_MAPS_API_KEY:
    raise EnvironmentError(
        "GOOGLE_MAPS_API_KEY is not set. Copy .env.example to .env and add "
        "your Google Maps API key before running this project."
    )

# ---------------------------------------------------------------------------
# Geographic search parameters — defaults target Ranchi's main city area.
# Ranchi main city (Firayalal / Main Road / Albert Ekka Chowk / Kutchery
# area) fits comfortably inside a ~12 km radius from this center point.
# ---------------------------------------------------------------------------
SEARCH_LAT = float(os.getenv("SEARCH_LAT", "23.3441"))
SEARCH_LNG = float(os.getenv("SEARCH_LNG", "85.3096"))
SEARCH_RADIUS_METERS = int(os.getenv("SEARCH_RADIUS_METERS", "12000"))

# Google's Nearby Search hard limit is 50,000 m — enforce it defensively.
if not (0 < SEARCH_RADIUS_METERS <= 50000):
    raise ValueError("SEARCH_RADIUS_METERS must be between 1 and 50000.")

# Delay before a next_page_token is usable. Google explicitly states the
# token needs a short warm-up period; requesting too early returns
# INVALID_REQUEST. 2 seconds is the commonly recommended minimum.
PAGE_TOKEN_DELAY_SECONDS = float(os.getenv("PAGE_TOKEN_DELAY_SECONDS", "2"))

# ---------------------------------------------------------------------------
# Place categories we care about for this task.
# `place_type` maps to Google's official "type" query parameter.
# `keyword` is an extra free-text hint that improves recall — Google's
# `electric_vehicle_charging_station` type is well supported, but adding the
# keyword helps catch listings that are tagged inconsistently.
# ---------------------------------------------------------------------------
SEARCH_TARGETS = [
    {
        "label": "petrol_pumps",
        "place_type": "gas_station",
        "keyword": "petrol pump",
    },
    {
        "label": "ev_stations",
        "place_type": "electric_vehicle_charging_station",
        "keyword": "EV charging station",
    },
]

# ---------------------------------------------------------------------------
# Output locations. Resolved relative to the project root (parent of src/).
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / os.getenv("DATA_DIR", "data")
MAPS_DIR = PROJECT_ROOT / os.getenv("MAPS_DIR", "maps")

DATA_DIR.mkdir(parents=True, exist_ok=True)
MAPS_DIR.mkdir(parents=True, exist_ok=True)

MAP_OUTPUT_FILE = MAPS_DIR / "ranchi_locations.html"

# ---------------------------------------------------------------------------
# Google Places API endpoint (legacy "Nearby Search", still fully supported
# and the most straightforward for next_page_token-based pagination).
# ---------------------------------------------------------------------------
NEARBY_SEARCH_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

# HTTP behaviour
REQUEST_TIMEOUT_SECONDS = 10
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2
