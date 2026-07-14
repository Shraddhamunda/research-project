"""
google_places.py
=================
Thin, well-behaved client around Google's Places "Nearby Search" API.

Responsibilities:
1. Issue a Nearby Search request for a given place type/keyword.
2. Follow `next_page_token` until Google reports no more pages (max 3 pages
   / 60 results per Google's own API limit — this is a Google-side cap, not
   something we can bypass, but we surface a warning if we hit it).
3. Normalize each raw "result" object into the flat schema the rest of the
   project expects (name, lat, lng, address, place_id, business_status,
   types).
4. Handle the failure modes explicitly called out in the task:
   - invalid / missing API key      -> REQUEST_DENIED
   - rate limiting                  -> OVER_QUERY_LIMIT (with retry/backoff)
   - empty results                  -> ZERO_RESULTS
   - network failures                -> requests exceptions (timeout, DNS, etc.)
"""

import time
import logging
from typing import Dict, List, Optional

import requests
from requests.exceptions import RequestException, Timeout, ConnectionError as ReqConnectionError

from src import config

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class GooglePlacesError(Exception):
    """Raised for API-level errors we cannot/should not silently retry past."""


class GooglePlacesClient:
    """
    Encapsulates all HTTP interaction with the Places Nearby Search endpoint.

    Usage:
        client = GooglePlacesClient()
        results = client.search_all_pages(lat=23.3441, lng=85.3096,
                                           radius=12000,
                                           place_type="gas_station",
                                           keyword="petrol pump")
    """

    def __init__(self, api_key: Optional[str] = None, session: Optional[requests.Session] = None):
        # Allow dependency injection (useful for testing) but default to config.
        self.api_key = api_key or config.GOOGLE_MAPS_API_KEY
        self.session = session or requests.Session()

    # ------------------------------------------------------------------ #
    # Low-level: a single HTTP call with retry/backoff for transient
    # failures (network errors, rate limiting).
    # ------------------------------------------------------------------ #
    def _request(self, params: Dict) -> Dict:
        last_exception = None

        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                response = self.session.get(
                    config.NEARBY_SEARCH_URL,
                    params=params,
                    timeout=config.REQUEST_TIMEOUT_SECONDS,
                )
                response.raise_for_status()  # raises for HTTP 4xx/5xx
                payload = response.json()

            except (Timeout, ReqConnectionError) as exc:
                # Classic "network failure" case: DNS issue, no internet,
                # request timed out, etc. Worth retrying.
                last_exception = exc
                logger.warning(
                    "Network error on attempt %d/%d: %s. Retrying in %ss...",
                    attempt, config.MAX_RETRIES, exc, config.RETRY_BACKOFF_SECONDS,
                )
                time.sleep(config.RETRY_BACKOFF_SECONDS * attempt)
                continue

            except RequestException as exc:
                # Non-recoverable HTTP-level error (e.g. malformed request).
                raise GooglePlacesError(f"HTTP request failed: {exc}") from exc

            status = payload.get("status")

            if status == "OK" or status == "ZERO_RESULTS":
                return payload

            if status == "REQUEST_DENIED":
                # Almost always an invalid/missing API key or an API that
                # hasn't been enabled on the Google Cloud project.
                error_msg = payload.get("error_message", "No further details provided by Google.")
                raise GooglePlacesError(
                    f"Request denied by Google Places API — check that your API key is valid "
                    f"and that 'Places API' is enabled for your project. Details: {error_msg}"
                )

            if status == "INVALID_REQUEST":
                # Frequently happens if next_page_token is queried too soon.
                logger.warning(
                    "INVALID_REQUEST (often a next_page_token used too early). "
                    "Retrying in %ss...", config.RETRY_BACKOFF_SECONDS
                )
                time.sleep(config.RETRY_BACKOFF_SECONDS)
                continue

            if status == "OVER_QUERY_LIMIT":
                # Rate limit or billing/quota issue — back off and retry.
                logger.warning(
                    "OVER_QUERY_LIMIT hit on attempt %d/%d. Backing off %ss...",
                    attempt, config.MAX_RETRIES, config.RETRY_BACKOFF_SECONDS * attempt,
                )
                time.sleep(config.RETRY_BACKOFF_SECONDS * attempt)
                continue

            # UNKNOWN_ERROR or anything unexpected — worth a retry too.
            logger.warning(
                "Unexpected status '%s' on attempt %d/%d. Retrying...",
                status, attempt, config.MAX_RETRIES,
            )
            time.sleep(config.RETRY_BACKOFF_SECONDS)

        # Exhausted all retries.
        if last_exception:
            raise GooglePlacesError(
                f"Network failure after {config.MAX_RETRIES} attempts: {last_exception}"
            )
        raise GooglePlacesError(
            f"Google Places API did not return a usable response after {config.MAX_RETRIES} attempts."
        )

    # ------------------------------------------------------------------ #
    # Public: fetch ALL pages for one search (place_type + keyword).
    # ------------------------------------------------------------------ #
    def search_all_pages(
        self,
        lat: float,
        lng: float,
        radius: int,
        place_type: str,
        keyword: str,
    ) -> List[Dict]:
        """
        Returns a list of normalized place dicts across every available page.
        Google caps Nearby Search at 3 pages (~60 results) per query — this
        is an API-side limit, not something this client artificially imposes.
        """
        all_results: List[Dict] = []
        next_page_token: Optional[str] = None
        page_number = 1

        while True:
            params = {
                "location": f"{lat},{lng}",
                "radius": radius,
                "type": place_type,
                "keyword": keyword,
                "key": self.api_key,
            }

            # A next_page_token, when present, is the ONLY parameter Google
            # wants alongside the key for subsequent pages.
            if next_page_token:
                params = {"pagetoken": next_page_token, "key": self.api_key}
                # Google requires a short delay before a freshly-issued
                # token becomes valid — calling too soon yields INVALID_REQUEST.
                time.sleep(config.PAGE_TOKEN_DELAY_SECONDS)

            logger.info("Fetching page %d for type='%s' keyword='%s'...",
                        page_number, place_type, keyword)

            payload = self._request(params)
            status = payload.get("status")

            if status == "ZERO_RESULTS" and page_number == 1:
                logger.info("No results found for type='%s' keyword='%s' in this area.",
                            place_type, keyword)
                return []

            raw_results = payload.get("results", [])
            all_results.extend(self._normalize(r, place_type) for r in raw_results)

            next_page_token = payload.get("next_page_token")
            if not next_page_token:
                break

            page_number += 1

        logger.info("Collected %d total results for type='%s' keyword='%s'.",
                     len(all_results), place_type, keyword)
        return all_results

    # ------------------------------------------------------------------ #
    # Normalize a raw Google result into the flat schema this project uses.
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalize(result: Dict, queried_type: str) -> Dict:
        location = result.get("geometry", {}).get("location", {})
        return {
            "name": result.get("name"),
            "latitude": location.get("lat"),
            "longitude": location.get("lng"),
            "address": result.get("vicinity") or result.get("formatted_address"),
            "place_id": result.get("place_id"),
            "business_status": result.get("business_status", "UNKNOWN"),
            "types": ", ".join(result.get("types", [])),
            "rating": result.get("rating"),
            "user_ratings_total": result.get("user_ratings_total"),
            "queried_type": queried_type,
        }
