"""Solar-system security lookup for fixed-location sites (COSMOS complexes).

COSMOS sites sit in named systems instead of spawning by security band, so their Space
column needs each system's security status and region. ``data/systems.json`` is a tracked
cache that parse and build read offline::

    {"Hjoramold": {"security": 0.5092, "region": "Metropolis"},
     "E-8CSQ": {"kind": "constellation", "security": -0.08, "min_security": -0.41, "region": "Vale of the Silent"}}

A few pages name a constellation instead of a system; those entries carry the highest and
lowest member-system security. The fetch stage (``python -m scraper fetch`` / ``refresh``)
keeps the file in step with the pages: it collects candidate names from the cached COSMOS
pages (``scraper.parse.system_candidates``), resolves the new ones through ESI
(https://esi.evetech.net) and drops entries no page mentions any more. Candidates that are
neither systems nor constellations are not stored, so they are simply re-checked next time.

    uv run python -m scraper.systems   # resolve new names from the current raw cache
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from collections.abc import Iterable, Mapping
from pathlib import Path

from scraper.wiki import REQUEST_DELAY_S, ROOT, USER_AGENT, WIKI_DIR, load_category_index

ESI = "https://esi.evetech.net/latest"
SYSTEMS_FILE = ROOT / "data" / "systems.json"
IDS_CHUNK = 500  # POST /universe/ids/ accepts at most 500 names per call


# --------------------------------------------------------------------------- pure helpers
def security_class(security: float, region: str = "") -> str:
    """Return ``High`` / ``Low`` / ``Null`` (or ``Pochven``) the way the game rounds security status.

    A system is high-sec from 0.45 (shown as 0.5), null-sec at 0.0 and below, low-sec between.
    """
    if region == "Pochven":
        return "Pochven"
    if security <= 0.0:
        return "Null"
    if security >= 0.45:
        return "High"
    return "Low"


def lookup(candidates: Iterable[str], systems: Mapping[str, Mapping]) -> dict | None:
    """The first candidate that is a known system: ``{"name", "security", "region"}`` or None."""
    index = {name.lower(): name for name in systems}
    for candidate in candidates:
        name = index.get(candidate.lower())
        if name is not None:
            return {"name": name, **systems[name]}
    return None


def bands(high: float, low: float, region: str = "") -> str:
    """Security bands spanned by systems whose security lies in ``[low, high]``: ``High, Low`` ..."""
    order = ("High", "Low", "Null")
    top, bottom = security_class(high, region), security_class(low, region)
    if top not in order or bottom not in order:
        return top
    return ", ".join(order[order.index(top) : order.index(bottom) + 1])


def space_label(system: Mapping) -> str:
    """Space column text for a fixed-location site: ``High (Hjoramold, Metropolis)``.

    Constellation entries read ``Null (E-8CSQ constellation, Vale of the Silent)``.
    """
    region = str(system.get("region") or "")
    security = float(system["security"])
    if system.get("kind") == "constellation":
        label = bands(security, float(system.get("min_security", security)), region)
        name = f"{system['name']} constellation"
    else:
        label = security_class(security, region)
        name = str(system["name"])
    where = ", ".join(p for p in (name, region) if p)
    return f"{label} ({where})"


# --------------------------------------------------------------------------- cache file
def load_systems(path: Path | None = None) -> dict[str, dict]:
    """Load the tracked cache (required: parse and build run offline from it)."""
    path = path or SYSTEMS_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"system table not found at {path}; it is a tracked input "
            "(restore it from git, or run `uv run python -m scraper.systems` to rebuild it)"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def save_systems(systems: Mapping[str, Mapping], path: Path | None = None) -> None:
    path = path or SYSTEMS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {name: dict(systems[name]) for name in sorted(systems, key=str.lower)}
    path.write_text(json.dumps(ordered, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- ESI
def esi(path: str, body: object | None = None) -> object:
    """GET (or POST ``body`` as JSON) an ESI route such as ``/universe/systems/30002075/``."""
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        f"{ESI}{path}?datasource=tranquility",
        data=data,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json", "Content-Type": "application/json"},
        method="POST" if data is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


class _Esi:
    """Memoised ESI lookups for one resolve() run (systems, constellations, region names)."""

    def __init__(self) -> None:
        self.systems: dict[int, dict] = {}
        self.constellations: dict[int, dict] = {}
        self.regions: dict[int, str] = {}

    def _get(self, path: str) -> dict:
        data = esi(path)
        time.sleep(REQUEST_DELAY_S)
        return data  # type: ignore[return-value]

    def system(self, system_id: int) -> dict:
        if system_id not in self.systems:
            self.systems[system_id] = self._get(f"/universe/systems/{system_id}/")
        return self.systems[system_id]

    def constellation(self, constellation_id: int) -> dict:
        if constellation_id not in self.constellations:
            self.constellations[constellation_id] = self._get(f"/universe/constellations/{constellation_id}/")
        return self.constellations[constellation_id]

    def region(self, region_id: int) -> str:
        if region_id not in self.regions:
            self.regions[region_id] = str(self._get(f"/universe/regions/{region_id}/")["name"])
        return self.regions[region_id]


def resolve(names: Iterable[str]) -> dict[str, dict]:
    """Resolve exact system (or constellation) names through ESI into cache entries.

    Names that are neither (factions, regions, plain words) are left out.
    """
    wanted = sorted({n.strip() for n in names if n and n.strip() and len(n.strip()) <= 100})
    hits: dict[str, dict[str, int]] = {"systems": {}, "constellations": {}}
    for i in range(0, len(wanted), IDS_CHUNK):
        data = esi("/universe/ids/", wanted[i : i + IDS_CHUNK])
        time.sleep(REQUEST_DELAY_S)
        for kind, found in hits.items():
            for hit in data.get(kind, []) if isinstance(data, dict) else []:
                found[str(hit["name"])] = int(hit["id"])
    cache = _Esi()
    out: dict[str, dict] = {}
    for name, system_id in sorted(hits["systems"].items()):
        info = cache.system(system_id)
        region_id = int(cache.constellation(int(info["constellation_id"]))["region_id"])
        out[name] = {"security": round(float(info["security_status"]), 4), "region": cache.region(region_id)}
    for name, constellation_id in sorted(hits["constellations"].items()):
        if name in out:
            continue  # a system of the same name wins
        info = cache.constellation(constellation_id)
        securities = [float(cache.system(int(s))["security_status"]) for s in info.get("systems", [])]
        if not securities:
            continue
        out[name] = {
            "kind": "constellation",
            "security": round(max(securities), 4),
            "min_security": round(min(securities), 4),
            "region": cache.region(int(info["region_id"])),
        }
    return out


def cosmos_candidates(wiki_dir: Path = WIKI_DIR) -> set[str]:
    """Every system-name candidate on the cached COSMOS pages."""
    from scraper import parse  # local import: parse imports this module

    category_index = load_category_index()
    names: set[str] = set()
    for path in sorted(wiki_dir.glob("*.wiki")):
        title, text = parse.read_page(path)
        if parse.COSMOS_CATEGORY not in parse.page_categories(title, text, category_index):
            continue
        _kind, infobox = parse.parse_infobox(text)
        names.update(parse.system_candidates(infobox.get("location", ""), text, title))
    return names


def refresh(wiki_dir: Path = WIKI_DIR, path: Path | None = None) -> int:
    """Bring ``data/systems.json`` in step with the cached COSMOS pages; returns how many entries were added.

    New candidate names are resolved through ESI; entries no page mentions any more are dropped.
    """
    path = path or SYSTEMS_FILE
    systems = load_systems(path) if path.exists() else {}
    candidates = cosmos_candidates(wiki_dir)
    wanted = {n.lower() for n in candidates}
    kept = {name: info for name, info in systems.items() if name.lower() in wanted}
    known = {name.lower() for name in kept}
    unknown = sorted(n for n in candidates if n.lower() not in known)
    added = resolve(unknown) if unknown else {}
    kept.update(added)
    save_systems(kept, path)
    dropped = len(systems) - (len(kept) - len(added))
    print(
        f"systems: {len(kept)} known, {len(added)} added, {dropped} dropped "
        f"({len(unknown)} unresolved candidate names checked against ESI)"
    )
    return len(added)


if __name__ == "__main__":
    refresh()
    sys.exit(0)
