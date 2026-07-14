"""
main.py
=======
Entry point that ties everything together:

    config  -->  google_places  -->  exporter  -->  map_visualizer

Run with:  python main.py
"""

import logging
import sys

from src import config
from src.google_places import GooglePlacesClient, GooglePlacesError
from src.exporter import export_records
from src.map_visualizer import build_map

logger = logging.getLogger(__name__)


def collect_all() -> dict:
    """
    Runs a Nearby Search (with full pagination) for every entry in
    config.SEARCH_TARGETS and returns a dict keyed by label:
        {"petrol_pumps": [...], "ev_stations": [...]}
    """
    client = GooglePlacesClient()
    dataset = {}

    for target in config.SEARCH_TARGETS:
        label = target["label"]
        try:
            results = client.search_all_pages(
                lat=config.SEARCH_LAT,
                lng=config.SEARCH_LNG,
                radius=config.SEARCH_RADIUS_METERS,
                place_type=target["place_type"],
                keyword=target["keyword"],
            )
        except GooglePlacesError as exc:
            # Surface the error clearly but don't crash the whole pipeline —
            # e.g. if EV stations fail we still want petrol pump data saved.
            logger.error("Failed to collect '%s': %s", label, exc)
            results = []

        dataset[label] = results

    return dataset


def main():
    logger.info(
        "Starting collection for Ranchi main city (center=%s,%s radius=%sm)...",
        config.SEARCH_LAT, config.SEARCH_LNG, config.SEARCH_RADIUS_METERS,
    )

    dataset = collect_all()

    # Fail loudly (but gracefully) if EVERYTHING came back empty — likely a
    # config/key problem rather than a genuine "no results" situation.
    if all(len(v) == 0 for v in dataset.values()):
        logger.warning(
            "No results were returned for ANY category. This usually means "
            "the API key is invalid, billing isn't enabled on the Google "
            "Cloud project, or the Places API isn't enabled. Check the "
            "logs above for the specific error."
        )

    for label, records in dataset.items():
        export_records(records, config.DATA_DIR, label)

    build_map(dataset)

    logger.info("Done. Data in '%s/', map in '%s/'.", config.DATA_DIR, config.MAPS_DIR)


if __name__ == "__main__":
    try:
        main()
    except EnvironmentError as exc:
        # Raised by config.py if GOOGLE_MAPS_API_KEY is missing.
        logger.error(str(exc))
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")
        sys.exit(130)
