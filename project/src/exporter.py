"""
exporter.py
===========
Handles persisting collected place records to disk in both CSV and JSON
formats. Kept separate from google_places.py so the API client stays
focused purely on "talk to Google" and this module stays focused purely on
"write to disk" — easy to unit test and easy to swap later (e.g. write to a
database instead) without touching the collection logic.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List

import pandas as pd

logger = logging.getLogger(__name__)

# Column order kept consistent across CSV/JSON for readability downstream.
COLUMNS = [
    "name",
    "latitude",
    "longitude",
    "address",
    "place_id",
    "business_status",
    "types",
    "rating",
    "user_ratings_total",
    "queried_type",
]


def export_records(records: List[Dict], base_path: Path, label: str) -> None:
    """
    Writes `records` to `<base_path>/<label>.csv` and `<base_path>/<label>.json`.

    Handles the "empty results" case gracefully: if `records` is empty we
    still write empty-but-valid CSV/JSON files (with headers) so downstream
    pipelines don't break on a missing file, and we log a clear warning
    instead of silently doing nothing.
    """
    base_path.mkdir(parents=True, exist_ok=True)
    csv_path = base_path / f"{label}.csv"
    json_path = base_path / f"{label}.json"

    if not records:
        logger.warning("No records found for '%s' — writing empty output files.", label)
        pd.DataFrame(columns=COLUMNS).to_csv(csv_path, index=False)
        json_path.write_text(json.dumps([], indent=2), encoding="utf-8")
        return

    df = pd.DataFrame(records)
    # Ensure consistent column order/presence even if some keys were missing.
    df = df.reindex(columns=COLUMNS)

    # De-duplicate by place_id — Nearby Search can return overlapping
    # results across pages/keyword variants.
    before = len(df)
    df = df.drop_duplicates(subset="place_id").reset_index(drop=True)
    if len(df) < before:
        logger.info("Removed %d duplicate record(s) for '%s'.", before - len(df), label)

    df.to_csv(csv_path, index=False)
    json_path.write_text(
        json.dumps(df.to_dict(orient="records"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Saved %d records -> %s and %s", len(df), csv_path, json_path)
