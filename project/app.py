"""
app.py
======
Minimal HTTP wrapper around the already-collected station data.

This is the ONLY new backend file. It does NOT re-query Google, does not
touch main.py / src/google_places.py / src/exporter.py / src/map_visualizer.py,
and does not change your existing pipeline in any way.

It simply serves the JSON files that `python main.py` already produces
(data/ev_stations.json, data/petrol_pumps.json) over HTTP, with optional
distance-sorting so the frontend can ask "give me these stations sorted
by distance from here" without needing its own geo logic.

Setup
-----
    pip install -r requirements-api.txt   (flask + flask-cors — see that file)
    python main.py        # (unchanged) — populates data/*.json at least once
    python app.py          # starts the API on http://localhost:5000

Endpoints
---------
GET /api/health
    -> {"status": "ok"}

GET /api/stations?type=ev|petrol|diesel&lat=<float>&lng=<float>
    type   REQUIRED. "ev" reads data/ev_stations.json.
                      "petrol" / "diesel" both read data/petrol_pumps.json
                      (same physical stations sell both fuels; no separate
                      diesel dataset exists in the collector).
    lat,lng OPTIONAL. If provided, every station gets a `distance_km` field
                      (straight-line Haversine distance) and the list is
                      sorted nearest-first. If omitted, stations are
                      returned in their on-disk order, unsorted.

    Response shape:
    {
      "type": "ev",
      "count": 12,
      "stations": [
        {
          "name": "...", "latitude": 23.37, "longitude": 85.32,
          "address": "...", "place_id": "...", "business_status": "OPERATIONAL",
          "types": "point_of_interest, establishment", "rating": 3.9,
          "user_ratings_total": 11.0, "queried_type": "electric_vehicle_charging_station",
          "distance_km": 2.14        // only present when lat/lng were given
        },
        ...
      ]
    }
"""

import json
import math
import os
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

from src import config

app = Flask(__name__)
CORS(app)  # allow the Vite dev server (a different origin) to call this API

DATA_FILES = {
    "ev": config.DATA_DIR / "ev_stations.json",
    "petrol": config.DATA_DIR / "petrol_pumps.json",
    "diesel": config.DATA_DIR / "petrol_pumps.json",
}


def load_stations(kind: str):
    path: Path = DATA_FILES[kind]
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance in km. Used only for quick sorting/estimation —
    actual driving distance/ETA comes from Google Directions on the frontend."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/stations", methods=["GET"])
def get_stations():
    kind = (request.args.get("type") or "").lower()
    if kind not in DATA_FILES:
        return jsonify({"error": "type must be one of: ev, petrol, diesel"}), 400

    stations = load_stations(kind)

    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)

    if lat is not None and lng is not None:
        enriched = []
        for s in stations:
            if s.get("latitude") is not None and s.get("longitude") is not None:
                s = {**s, "distance_km": round(
                    haversine_km(lat, lng, s["latitude"], s["longitude"]), 2
                )}
                enriched.append(s)
        enriched.sort(key=lambda s: s["distance_km"])
        stations = enriched

    return jsonify({"type": kind, "count": len(stations), "stations": stations})


if __name__ == "__main__":
    port = int(os.environ.get("PORT",5000))
    app.run(host="0.0.0.0", port=port)
