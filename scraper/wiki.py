"""Thin client for the EVE University wiki MediaWiki API.

Downloads category member lists and page wikitext into ``data/raw/wiki``.
The cache is git-ignored; run ``uv run python -m scraper.fetch`` to refresh it.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from collections.abc import Iterable
from pathlib import Path

API = "https://wiki.eveuniversity.org/api.php"
USER_AGENT = "expo-catalog/0.1 (+https://github.com/grimmy0/expo-catalog)"
REQUEST_DELAY_S = 0.5

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
WIKI_DIR = RAW_DIR / "wiki"
CATEGORY_FILE = RAW_DIR / "category_members.tsv"

# Categories whose main-namespace members are candidate sites.
SITE_CATEGORIES: tuple[str, ...] = (
    "DED_Complexes",
    "Unrated_Complexes",
    "Data_sites",
    "Relic_sites",
    "Gas_sites",
    "Chemical_Labs",
    "Wormhole_sites",
    "Combat_Anomalies",
    "Ore_sites",
    "Rare_ore_sites",
    "Removed_ore_sites",
    "Sovereignty_Hub_ore_deposits",
    "Ice_belts",
    "Homefront_Operations",
)

# Pages outside those categories that the catalog also needs.
EXTRA_PAGES: tuple[str, ...] = (
    "EDENCOM Scout Fleet",
    "Torpid Sleeper Hive",
    "Observatory Infiltration",
    "Deepflow rifts",
    "Epicenter",
    "Unknown Anomaly",
    "Phased Asteroid Field",
    "Asteroid Belt Remnants",
    "Jove Observatory",
    "Original Drifter Combat Anomalies",
    # Incursions
    "Distress Beacon",
    "Forward Reconnaissance Outpost",
    "Propaganda Cluster",
    "Nation Commander Outpost",
    "Nation Mining Colony",
    "Override Transfer Array",
    "Nation Commander Stronghold",
    "Nation Consolidation Network",
    "Overwhelmed Civilian Facility",
    "Nation Rebirth Facility",
    "True Creations Research Center",
    "True Power Provisional Headquarters",
    "The Kundalini Manifest",
    "Uroborus",
    # Rogue drones, Drifters, misc
    "Rogue Drone Outgrowth Colony",
    "Rampant Drone Fabricator",
    "Drifter Hive(Barbican)",
    "Drifter Hive Anomaly",
    "Stronghold",
    "Hrada-Oki Bivouac",
    "Serpentis Capital Staging",
)

# Templates whose wikitext the parser needs (saved directly under RAW_DIR).
TEMPLATE_PAGES: tuple[str, ...] = ("Template:Whisk",)


def safe_filename(title: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", title).strip("_")[:150]


def api(params: dict[str, str]) -> dict:
    query = dict(params, format="json", formatversion="2")
    url = API + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def category_members(category: str) -> list[str]:
    """Return main-namespace page titles in ``Category:<category>``."""
    titles: list[str] = []
    params = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": f"Category:{category}",
        "cmlimit": "500",
        "cmnamespace": "0",
    }
    while True:
        data = api(params)
        titles += [m["title"] for m in data.get("query", {}).get("categorymembers", [])]
        cont = data.get("continue")
        if not cont:
            return titles
        params = dict(params, **cont)
        time.sleep(REQUEST_DELAY_S)


def fetch_pages(titles: Iterable[str], out_dir: Path = WIKI_DIR) -> dict[str, str | None]:
    """Download wikitext for ``titles``; returns {requested title: resolved title or None}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    titles = list(dict.fromkeys(titles))
    resolved: dict[str, str | None] = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i : i + 50]
        data = api(
            {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content",
                "rvslots": "main",
                "titles": "|".join(chunk),
                "redirects": "1",
            }
        )
        query = data.get("query", {})
        redirects = {r["from"]: r["to"] for r in query.get("redirects", [])}
        normalized = {n["from"]: n["to"] for n in query.get("normalized", [])}
        found: dict[str, str] = {}
        for page in query.get("pages", []):
            if page.get("missing"):
                continue
            found[page["title"]] = page["revisions"][0]["slots"]["main"]["content"]
        for title in chunk:
            target = normalized.get(title, title)
            target = redirects.get(target, target)
            if target in found:
                text = f"<!-- TITLE: {target} -->\n" + found[target]
                (out_dir / (safe_filename(title) + ".wiki")).write_text(text, encoding="utf-8")
                resolved[title] = target
            else:
                resolved[title] = None
        time.sleep(REQUEST_DELAY_S)
    return resolved


def fetch_all() -> None:
    """Refresh the whole raw cache: category lists, every member page, needed templates."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, str]] = []
    for category in SITE_CATEGORIES:
        for title in category_members(category):
            rows.append((category, title))
        time.sleep(REQUEST_DELAY_S)
    CATEGORY_FILE.write_text("".join(f"{c}\t{t}\n" for c, t in rows), encoding="utf-8")
    titles = sorted({t for _, t in rows} | set(EXTRA_PAGES))
    resolved = fetch_pages(titles)
    fetch_pages(TEMPLATE_PAGES, out_dir=RAW_DIR)
    missing = [t for t, r in resolved.items() if r is None]
    print(f"fetched {len(titles) - len(missing)} pages, {len(missing)} missing: {missing}")


def load_category_index() -> dict[str, set[str]]:
    """Return {page title: {category, ...}} from the cached TSV."""
    index: dict[str, set[str]] = {}
    if not CATEGORY_FILE.exists():
        return index
    for line in CATEGORY_FILE.read_text(encoding="utf-8").splitlines():
        if "\t" not in line:
            continue
        category, title = line.split("\t", 1)
        index.setdefault(title, set()).add(category)
    return index
