"""
map_visualizer.py
==================
Builds an interactive Folium map showing every collected petrol pump and
EV charging station, with distinct marker styles per category, and saves
it as a standalone HTML file that opens in any browser (no server needed).
"""

import logging
from pathlib import Path
from typing import Dict, List

import folium
from folium.plugins import MarkerCluster

from src import config

logger = logging.getLogger(__name__)

# Visual encoding per category — distinct color + icon so the two point
# types are unmistakable at a glance, and legend text stays human-readable.
STYLE_MAP = {
    "petrol_pumps": {"color": "red", "icon": "tint", "label": "Petrol Pump"},
    "ev_stations": {"color": "green", "icon": "bolt", "label": "EV Charging Station"},
}


def build_map(dataset: Dict[str, List[Dict]], output_path: Path = config.MAP_OUTPUT_FILE) -> Path:
    """
    dataset: {"petrol_pumps": [...], "ev_stations": [...]}
    Returns the path to the saved HTML file.
    """
    fmap = folium.Map(
        location=[config.SEARCH_LAT, config.SEARCH_LNG],
        zoom_start=13,
        tiles="OpenStreetMap",
    )

    # Mark the search center for reference.
    folium.Marker(
        location=[config.SEARCH_LAT, config.SEARCH_LNG],
        popup="Search Center (Ranchi Main City)",
        icon=folium.Icon(color="blue", icon="crosshairs", prefix="fa"),
    ).add_to(fmap)

    total_plotted = 0

    for label, records in dataset.items():
        style = STYLE_MAP.get(label, {"color": "gray", "icon": "info-sign", "label": label})

        # Cluster markers so dense areas stay readable when zoomed out.
        cluster = MarkerCluster(name=style["label"] + "s").add_to(fmap)

        for rec in records:
            lat, lng = rec.get("latitude"), rec.get("longitude")
            if lat is None or lng is None:
                continue  # skip malformed/incomplete records defensively

            popup_html = (
                f"<b>{rec.get('name', 'Unknown')}</b><br>"
                f"{style['label']}<br>"
                f"{rec.get('address', '')}<br>"
                f"Status: {rec.get('business_status', 'UNKNOWN')}<br>"
                f"Place ID: {rec.get('place_id', '')}"
            )

            folium.Marker(
                location=[lat, lng],
                popup=folium.Popup(popup_html, max_width=300),
                tooltip=rec.get("name", style["label"]),
                icon=folium.Icon(color=style["color"], icon=style["icon"], prefix="fa"),
            ).add_to(cluster)

            total_plotted += 1

    folium.LayerControl(collapsed=False).add_to(fmap)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(output_path))
    logger.info("Plotted %d locations -> interactive map saved at %s", total_plotted, output_path)
    return output_path
