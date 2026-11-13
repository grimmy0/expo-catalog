"""Build ``src/expo_catalog/data/catalog.sqlite`` from ``data/parsed_sites.json`` plus curated data.

    uv run python -m scraper.build [--out PATH]

Pipeline: load parsed pages -> fold "(updated)" duplicates into their base page
-> drop index pages -> derive fields with ``scraper.rules`` -> apply
``scraper.curated.OVERRIDES`` and event overrides -> append generated families
-> write SQLite through ``expo_catalog.db``.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sqlite3
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from scraper import curated, rules
from scraper.parse import PARSED_FILE

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from expo_catalog import db  # noqa: E402  (src layout; importable once sys.path is set)

ALLOWED_CATEGORIES = set(db.CATEGORIES) | {"incursion"}
ALLOWED_STATUSES = set(db.STATUSES)
VERSION = "0.1.0"


# --------------------------------------------------------------------------- page -> record
def load_pages(path: Path = PARSED_FILE) -> dict[str, dict[str, Any]]:
    pages = json.loads(path.read_text(encoding="utf-8"))
    return {p["title"]: p for p in pages}


def fold_merges(pages: dict[str, dict[str, Any]]) -> None:
    """Fold "(updated)" duplicate pages into their base page in place."""
    for dup, base in curated.MERGE_INTO_BASE.items():
        d = pages.pop(dup, None)
        if d is None:
            continue
        b = pages.get(base)
        if b is None:
            d["title"] = base
            pages[base] = d
            continue
        if len(d.get("npc_rows", [])) >= len(b.get("npc_rows", [])):
            b["npc_rows"] = d["npc_rows"]
        if not b.get("infobox") and d.get("infobox"):
            b["infobox"] = d["infobox"]
            b["infobox_kind"] = d.get("infobox_kind")
        if not b.get("description") and d.get("description"):
            b["description"] = d["description"]
        b["blue_loot_isk"] = b.get("blue_loot_isk") or d.get("blue_loot_isk")


def page_record(page: Mapping[str, Any]) -> dict[str, Any]:
    title = str(page["title"])
    category, scan_group, is_sig = rules.classify(page)
    space = rules.space_of(page, category)
    faction = rules.faction_of(page)
    combat = category in (
        "combat_ded",
        "combat_unrated",
        "combat_anomaly",
        "chemical_lab",
        "wormhole_combat",
        "wormhole_data",
        "wormhole_relic",
        "pochven",
        "incursion",
        "homefront",
        "drifter",
        "event",
        "cosmos",
    )
    enemies, ewar, enemy_rows = rules.aggregate_enemies(page.get("npc_rows", []), faction, combat=combat)
    if title in rules.ENEMIES_FALLBACK:
        enemies = rules.ENEMIES_FALLBACK[title]  # hand-written prose beats a misleading table sum
    elif (
        enemies == "Unknown"
        and category == "cosmos"
        and page.get("npc_rows")
        and not any(r.get("hostile", True) for r in page["npc_rows"])
    ):
        enemies = "None (neutral NPCs only)"  # the tables list only non-hostile ships
    elif enemies == "Unknown":
        enemies = rules.enemies_fallback(title, category) or enemies
    elif enemies == "None" and category in ("data", "relic", "sleeper_cache", "ghost"):
        enemies = rules.hazard_enemies(page) or enemies
    danger = rules.danger_of(page, category, space)
    min_ship = rules.min_ship_of(page, category, space, danger)
    status = rules.status_of(page, category)
    escalation = ", ".join(page.get("escalations", [])[:3]) or None
    loot = None
    if page.get("blue_loot_isk"):
        loot = f"Blue loot ~{page['blue_loot_isk'] / 1e6:,.1f}M ISK"
    sig = page.get("infobox", {}).get("signature strength")
    not_strengths = ("n/a", "na", "", "anomaly", "100% anomaly")
    if category == "cosmos":  # COSMOS pages put "Beacon" / "Signature" / "Unknown" here; the scan group says it
        not_strengths += ("beacon", "signature", "unknown", "none")
    if sig and sig.lower() not in not_strengths:
        loot = (loot + "; " if loot else "") + f"Signature strength {sig}"
    return {
        "name": title,
        "category": category,
        "scan_group": scan_group,
        "is_signature": is_sig,
        "space": space,
        "faction": faction,
        "rating": rules.rating_of(page, category),
        "danger": danger,
        "danger_label": rules.DANGER_LABELS[danger],
        "enemies": enemies,
        "min_ship": min_ship,
        "ship_limit": rules.ship_limit_of(page),
        "ewar": ewar,
        "status": status,
        "escalation": escalation,
        "loot_note": loot,
        "description": (page.get("description") or None),
        "source_url": rules.source_url(title),
        "enemy_rows": enemy_rows,
    }


def apply_overrides(record: dict[str, Any], *override_sets: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    title = record["name"]
    for overrides in override_sets:
        for key, value in overrides.get(title, {}).items():
            record[key] = value
    record["danger_label"] = rules.DANGER_LABELS[int(record["danger"])]
    return record


def build_records(pages: dict[str, dict[str, Any]], events: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    pages = {t: dict(p) for t, p in pages.items()}
    fold_merges(pages)
    events = events if events is not None else curated.load_events()
    ev_overrides = curated.event_overrides(events)
    records: list[dict[str, Any]] = []
    for title in sorted(pages):
        if title in curated.EXCLUDE_TITLES:
            continue
        rec = page_record(pages[title])
        # Event-JSON overrides first; hand-written curated overrides are authoritative.
        records.append(apply_overrides(rec, ev_overrides, curated.OVERRIDES))
    records += curated.generated_sites(pages, events)
    records = dedupe(records)
    reconcile(records)
    return records


# Categories where "min ship" is a hacking/mining hull rather than something that clears the site.
NON_COMBAT_CATEGORIES = frozenset(
    {
        "data",
        "relic",
        "gas",
        "ore",
        "ice",
        "ghost",
        "sleeper_cache",
        "wormhole_gas",
        "wormhole_ore",
        "wormhole_connection",
    }
)


def consistency_issues(rec: Mapping[str, Any]) -> str | None:
    """Return a description of a danger / min-ship mismatch, or None when consistent."""
    if rec["category"] in NON_COMBAT_CATEGORIES or rec["scan_group"] == "Beacon" or rec["status"] == "unverified":
        return None
    danger = int(rec["danger"])
    tier = rules.ship_tier(str(rec["min_ship"]))
    if danger == 5 and tier < 6:
        return "danger 5 needs marauder/fleet"
    if danger == 4 and tier < 5:
        return "danger 4 needs battleship/T3C/gang"
    if danger == 2 and tier > 3:
        return "danger 2 should need at most a cruiser"
    if danger == 1 and tier > 0:
        return "danger 1 should need a non-combat hull"
    return None


def reconcile(records: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    """Fix danger/min-ship mismatches in place; returns (name, issue, action) for each change."""
    changes: list[tuple[str, str, str]] = []
    for rec in records:
        issue = consistency_issues(rec)
        if not issue:
            continue
        danger = int(rec["danger"])
        tier = rules.ship_tier(str(rec["min_ship"]))
        if danger >= 4:
            rec["min_ship"] = rules.tier_phrase(6 if danger == 5 else 5, danger)
            action = f"min_ship -> {rec['min_ship']}"
        elif danger == 2:
            rec["danger"] = 3 if tier <= 5 else 4
            action = f"danger -> {rec['danger']}"
        else:  # danger 1 with a combat hull: the site has rats, so it is at least Low
            rec["danger"] = 2
            action = "danger -> 2"
        rec["danger_label"] = rules.DANGER_LABELS[int(rec["danger"])]
        changes.append((rec["name"], issue, action))
    records.sort(key=lambda r: (r["name"].lower(), r["space"].lower()))
    reconcile.last_changes = changes  # type: ignore[attr-defined]
    return changes


def dedupe(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for rec in records:
        key = (rec["name"].lower(), rec["space"].lower())
        if key in seen:
            # Keep the richer record (more enemy rows / longer description).
            old = seen[key]
            if len(rec.get("enemy_rows", [])) > len(old.get("enemy_rows", [])):
                seen[key] = rec
            continue
        seen[key] = rec
    return list(seen.values())


def validate(records: list[dict[str, Any]]) -> None:
    problems: list[str] = []
    for rec in records:
        if not rec.get("name"):
            problems.append("empty name")
        if rec["category"] not in ALLOWED_CATEGORIES:
            problems.append(f"{rec['name']}: bad category {rec['category']}")
        if rec["scan_group"] not in db.SCAN_GROUPS:
            problems.append(f"{rec['name']}: bad scan group {rec['scan_group']}")
        if rec["status"] not in ALLOWED_STATUSES:
            problems.append(f"{rec['name']}: bad status {rec['status']}")
        if not (0 <= int(rec["danger"]) <= 5):
            problems.append(f"{rec['name']}: danger {rec['danger']}")
        if rec["danger_label"] != rules.DANGER_LABELS[int(rec["danger"])]:
            problems.append(f"{rec['name']}: label mismatch")
        for col in ("enemies", "min_ship", "space"):
            if not rec.get(col):
                problems.append(f"{rec['name']}: empty {col}")
    if problems:
        raise ValueError("invalid records:\n  " + "\n  ".join(problems[:40]))


def search_text(rec: Mapping[str, Any]) -> str:
    parts = [
        rec.get(k)
        for k in ("name", "category", "scan_group", "space", "faction", "rating", "status", "enemies", "min_ship")
    ]
    return " | ".join(str(p) for p in parts if p).lower()


# --------------------------------------------------------------------------- write
def write_db(records: list[dict[str, Any]], out: Path) -> sqlite3.Connection:
    if out.exists():
        out.unlink()
    out.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(out, readonly=False)
    db.create_schema(conn)
    for rec in sorted(records, key=lambda r: (r["name"].lower(), r["space"].lower())):
        row = {k: rec.get(k) for k in db.SITE_COLUMNS if k != "id"}
        row["search_text"] = search_text(rec)
        site_id = db.insert_site(conn, row)
        for enemy in rec.get("enemy_rows", []):
            if enemy.get("ship_class"):
                db.insert_enemy(conn, site_id, enemy)
    db.set_meta(conn, "built_at", dt.datetime.now(dt.UTC).isoformat(timespec="seconds"))
    db.set_meta(conn, "source", "EVE University wiki (wiki.eveuniversity.org) + EVE Ref SDE wormhole data + curated")
    db.set_meta(conn, "site_count", str(len(records)))
    db.set_meta(conn, "version", VERSION)
    conn.commit()
    return conn


def build(out: Path | None = None, parsed: Path = PARSED_FILE, events: list[dict[str, Any]] | None = None) -> Path:
    out = out or db.DEFAULT_DB_PATH
    records = build_records(load_pages(parsed), events)
    validate(records)
    conn = write_db(records, out)
    conn.close()
    return out


def report(out: Path) -> None:
    conn = db.connect(out)
    total = conn.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
    print(f"wrote {out} with {total} sites")
    print(f"{'category':22s} {'count':>5s}")
    for cat, n in conn.execute("SELECT category, COUNT(*) FROM sites GROUP BY category ORDER BY 2 DESC"):
        print(f"{cat:22s} {n:5d}")
    status = Counter(dict(conn.execute("SELECT status, COUNT(*) FROM sites GROUP BY status").fetchall()))
    print("status:", dict(status))
    changes = getattr(reconcile, "last_changes", [])
    print(f"consistency fixes applied: {len(changes)}")
    for name, issue, action in changes:
        print(f"  {name}: {issue} -> {action}")
    conn.close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output SQLite path (default src/expo_catalog/data/catalog.sqlite, the catalog bundled with the package)",
    )
    args = parser.parse_args(argv)
    out = build(args.out)
    report(out)


if __name__ == "__main__":
    main()
