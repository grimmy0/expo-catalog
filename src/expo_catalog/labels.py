"""Compact text labels for the Type and Space columns.

Pure string helpers shared by the TUI (:mod:`expo_catalog.app`) and the field
filters (:mod:`expo_catalog.query`); nothing here depends on Textual.
"""

from __future__ import annotations

import re

from expo_catalog.db import Site

__all__ = [
    "SPACE_WIDTH",
    "TYPE_WIDTH",
    "clip",
    "space_label",
    "type_label",
]

TYPE_WIDTH = 12
"""Width of the Type column; :func:`type_label` never exceeds it."""
SPACE_WIDTH = 14
"""Width of the Space column; :func:`space_label` clips to it by default."""

# Short labels for the Type column (≤ TYPE_WIDTH chars). combat_ded and
# combat_anomaly are derived from the rating instead, see type_label().
_TYPE_LABELS: dict[str, str] = {
    "combat_unrated": "Unrated",
    "data": "Data",
    "relic": "Relic",
    "gas": "Gas",
    "chemical_lab": "Chem lab",
    "ghost": "Ghost",
    "sleeper_cache": "Sleeper",
    "wormhole_combat": "WH combat",
    "wormhole_data": "WH data",
    "wormhole_relic": "WH relic",
    "wormhole_gas": "WH gas",
    "wormhole_ore": "WH ore",
    "ore": "Ore",
    "ice": "Ice",
    "fw_complex": "FW plex",
    "insurgency": "Insurgency",
    "homefront": "Homefront",
    "pochven": "Pochven",
    "drifter": "Drifter",
    "incursion": "Incursion",
    "event": "Event",
    "wormhole_connection": "Wormhole",
    "other": "Other",
}
_DED_RATING = re.compile(r"\b(\d{1,2}/10)\b")
_TIER_RATING = re.compile(r"\btier\s*(\d+)\b", re.IGNORECASE)


def clip(text: str, width: int) -> str:
    """Collapse whitespace and truncate ``text`` to ``width`` with an ellipsis."""
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


def type_label(site: Site) -> str:
    """Compact Type cell: ``DED 3/10``, ``Unrated``, ``Anom T4``, ``WH relic`` ..."""
    rating = site.rating or ""
    if site.category == "combat_ded":
        match = _DED_RATING.search(rating)
        return f"DED {match.group(1)}" if match else "DED"
    if site.category == "combat_anomaly":
        match = _TIER_RATING.search(rating)
        return f"Anom T{match.group(1)}" if match else "Anomaly"
    label = _TYPE_LABELS.get(site.category)
    if label is None:
        label = site.category.replace("_", " ").capitalize()
    return clip(label, TYPE_WIDTH)


def space_label(space: str, width: int = SPACE_WIDTH) -> str:
    """Space cell: as-is when it fits, else ``High/Low/Null`` style, else clipped."""
    text = " ".join(space.split())
    if len(text) <= width:
        return text
    compact = text.replace(", ", "/")
    if len(compact) <= width:
        return compact
    return clip(text, width)
