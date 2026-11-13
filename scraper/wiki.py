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
STATE_FILE = ROOT / "data" / "wiki_state.json"
"""Committed snapshot of the last fetched revision of every tracked page (see ``scraper.check``)."""

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
    "Incursions_sites",
    "COSMOS_sites",
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
    # Rogue drones, Drifters, misc
    "Rogue Drone Outgrowth Colony",
    "Rampant Drone Fabricator",
    "Drifter Hive(Barbican)",
    "Drifter Hive Anomaly",
    "Stronghold",
    "Hrada-Oki Bivouac",
    "Serpentis Capital Staging",
)

# Site pages are also discovered through their infobox template, so a page that lost (or never had)
# its topic category is still tracked. Discovered pages are tracked like EXTRA_PAGES (no category).
SITE_TEMPLATES: tuple[str, ...] = ("Template:CMBSiteInfo",)

# Template users in these categories are not catalog sites.
IGNORED_CATEGORIES: tuple[str, ...] = (
    "Expeditions",  # escalation destinations, delivered by the journal; never scanned or seen as anomalies
    "COSMOS_agents",  # agent pages that describe a COSMOS mission with the site infobox
    "Mercenary_Tactical_Operations",  # sites offered only to the owner of a Mercenary Den
)

# Individual template users that are not catalog records, with the reason.
IGNORED_PAGES: dict[str, str] = {
    "Crimson Harvest (2020)": "event overview; its sites come from data/event_sites.json",
    "Shining Flame Base": "event site; covered by data/event_sites.json",
    "Treacherous Collapsed Conduit": "event site; covered by data/event_sites.json",
    "Upwell Covert Research Facilities": "event site; covered by data/event_sites.json",
    "Molting Season": "escalation destination (type=escalation), not a signature",
    "Toxic Waste Scandal!": "escalation destination (type=expedition), not a signature",
    "Signal Source": "escalation destination (type=expedition, past content), not a signature",
}


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


def embedded_in(template: str) -> list[str]:
    """Return main-namespace page titles that transclude ``template`` (e.g. ``Template:CMBSiteInfo``)."""
    titles: list[str] = []
    params = {
        "action": "query",
        "list": "embeddedin",
        "eititle": template,
        "eilimit": "500",
        "einamespace": "0",
    }
    while True:
        data = api(params)
        titles += [m["title"] for m in data.get("query", {}).get("embeddedin", [])]
        cont = data.get("continue")
        if not cont:
            return titles
        params = dict(params, **cont)
        time.sleep(REQUEST_DELAY_S)


def _resolve_titles(chunk: list[str], query: dict) -> dict[str, str]:
    """Map each requested title to the title the API actually returned (normalisation + redirects)."""
    redirects = {r["from"]: r["to"] for r in query.get("redirects", [])}
    normalized = {n["from"]: n["to"] for n in query.get("normalized", [])}
    out: dict[str, str] = {}
    for title in chunk:
        target = normalized.get(title, title)
        out[title] = redirects.get(target, target)
    return out


def page_metadata(titles: Iterable[str]) -> dict[str, dict]:
    """Latest ``revid``/``timestamp`` for ``titles`` without downloading content.

    Returns {requested title: {"revid": int, "timestamp": str, "title": resolved title}}; pages
    missing on the wiki are left out.
    """
    titles = list(dict.fromkeys(titles))
    meta: dict[str, dict] = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i : i + 50]
        data = api(
            {
                "action": "query",
                "prop": "revisions",
                "rvprop": "ids|timestamp",
                "titles": "|".join(chunk),
                "redirects": "1",
            }
        )
        query = data.get("query", {})
        found = {p["title"]: p for p in query.get("pages", []) if not p.get("missing") and p.get("revisions")}
        for title, target in _resolve_titles(chunk, query).items():
            page = found.get(target)
            if page is None:
                continue
            rev = page["revisions"][0]
            meta[title] = {"revid": int(rev["revid"]), "timestamp": str(rev.get("timestamp", "")), "title": target}
        if i + 50 < len(titles):
            time.sleep(REQUEST_DELAY_S)
    return meta


def fetch_pages(
    titles: Iterable[str], out_dir: Path = WIKI_DIR, state: dict[str, dict] | None = None
) -> dict[str, str | None]:
    """Download wikitext for ``titles``; returns {requested title: resolved title or None}.

    When ``state`` is given it is filled with ``{requested title: {"revid", "timestamp"}}``.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    titles = list(dict.fromkeys(titles))
    resolved: dict[str, str | None] = {}
    for i in range(0, len(titles), 50):
        chunk = titles[i : i + 50]
        data = api(
            {
                "action": "query",
                "prop": "revisions",
                "rvprop": "content|ids|timestamp",
                "rvslots": "main",
                "titles": "|".join(chunk),
                "redirects": "1",
            }
        )
        query = data.get("query", {})
        found: dict[str, dict] = {}
        for page in query.get("pages", []):
            if page.get("missing") or not page.get("revisions"):
                continue
            found[page["title"]] = page["revisions"][0]
        for title, target in _resolve_titles(chunk, query).items():
            rev = found.get(target)
            if rev is None:
                resolved[title] = None
                continue
            text = f"<!-- TITLE: {target} -->\n" + rev["slots"]["main"]["content"]
            (out_dir / (safe_filename(title) + ".wiki")).write_text(text, encoding="utf-8")
            resolved[title] = target
            if state is not None and "revid" in rev:
                state[title] = {"revid": int(rev["revid"]), "timestamp": str(rev.get("timestamp", ""))}
        time.sleep(REQUEST_DELAY_S)
    return resolved


def tracked_titles(rows: Iterable[tuple[str, str]], discovered: Iterable[str] = ()) -> dict[str, list[str]]:
    """{title: sorted categories} for every category member, plus EXTRA_PAGES and ``discovered`` (no category)."""
    cats: dict[str, set[str]] = {}
    for category, title in rows:
        cats.setdefault(title, set()).add(category)
    for title in (*EXTRA_PAGES, *discovered):
        cats.setdefault(title, set())
    return {t: sorted(c) for t, c in sorted(cats.items())}


def discovered_titles(rows: Iterable[tuple[str, str]]) -> list[str]:
    """Pages using a SITE_TEMPLATES infobox that the categories and EXTRA_PAGES miss, minus the ignored ones."""
    known = {title for _category, title in rows} | set(EXTRA_PAGES) | set(IGNORED_PAGES)
    for category in IGNORED_CATEGORIES:
        known.update(category_members(category))
        time.sleep(REQUEST_DELAY_S)
    found: set[str] = set()
    for template in SITE_TEMPLATES:
        found.update(t for t in embedded_in(template) if t not in known)
        time.sleep(REQUEST_DELAY_S)
    return sorted(found)


def site_membership() -> tuple[list[tuple[str, str]], dict[str, list[str]]]:
    """Live membership: the (category, title) rows of SITE_CATEGORIES and the full tracked-title map.

    Shared by ``fetch_all`` and ``scraper.check`` so both track exactly the same pages.
    """
    rows: list[tuple[str, str]] = []
    for category in SITE_CATEGORIES:
        rows += [(category, title) for title in category_members(category)]
        time.sleep(REQUEST_DELAY_S)
    return rows, tracked_titles(rows, discovered_titles(rows))


def load_state(path: Path | None = None) -> dict[str, dict]:
    path = path or STATE_FILE  # resolved at call time, so tests can point STATE_FILE elsewhere
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(state: dict[str, dict], path: Path | None = None) -> None:
    path = path or STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = {t: state[t] for t in sorted(state)}
    path.write_text(json.dumps(ordered, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def fetch_all() -> None:
    """Refresh the whole raw cache: category lists, every member page, wiki state."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    rows, tracked = site_membership()
    CATEGORY_FILE.write_text("".join(f"{c}\t{t}\n" for c, t in rows), encoding="utf-8")
    revisions: dict[str, dict] = {}
    resolved = fetch_pages(list(tracked), state=revisions)
    state = {
        t: {"revid": revisions[t]["revid"], "timestamp": revisions[t]["timestamp"], "categories": tracked[t]}
        for t in tracked
        if t in revisions
    }
    save_state(state)
    missing = [t for t, r in resolved.items() if r is None]
    print(f"fetched {len(tracked) - len(missing)} pages, {len(missing)} missing: {missing}")
    print(f"wrote {STATE_FILE.relative_to(ROOT)} ({len(state)} tracked pages)")


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
