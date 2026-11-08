"""Unit tests for scraper.rules and an integration test for scraper.build."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

from scraper import build, rules
from scraper.parse import PARSED_FILE

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def page(title: str, categories: list[str] | None = None, infobox: dict | None = None, rows: list[dict] | None = None,
         flags: dict | None = None) -> dict:
    return {"title": title, "categories": categories or [], "infobox": infobox or {}, "npc_rows": rows or [],
            "flags": flags or {}, "escalations": [], "description": "", "blue_loot_isk": None}


def row(cls: str, lo: int | None, hi: int | None, name: str = "x", **kw) -> dict:
    return {"section": kw.get("section"), "wave": kw.get("wave", "Wave 1"), "ship_class": cls, "count_min": lo,
            "count_max": hi, "name": name, "tier": kw.get("tier"), "hostile": kw.get("hostile", True),
            "ewar": kw.get("ewar", []), "trigger": None}


# --------------------------------------------------------------------------- classify
@pytest.mark.parametrize(
    "title, cats, itype, expected",
    [
        ("Serpentis Narcotic Warehouses", ["DED Complexes"], "ded", ("combat_ded", "Combat Site", 1)),
        ("Angel Vigil", ["Unrated Complexes"], "unrated", ("combat_unrated", "Combat Site", 1)),
        ("Ancient Ruins", ["Relic sites", "Unrated Complexes"], "combat relic", ("relic", "Relic Site", 1)),
        ("Angel Hideaway", ["Combat Anomalies"], "anomaly", ("combat_anomaly", "Combat Anomaly", 0)),
        ("Blood Forlorn Den", ["Unrated Complexes"], "", ("combat_anomaly", "Combat Anomaly", 0)),  # wiki mis-category
        ("Forgotten Perimeter Gateway", ["Wormhole sites"], "", ("wormhole_relic", "Relic Site", 1)),
        ("Unsecured Frontier Database", ["Wormhole sites"], "", ("wormhole_data", "Data Site", 1)),
        ("Perimeter Hangar", ["Wormhole sites"], "", ("wormhole_combat", "Combat Anomaly", 0)),
        ("Barren Perimeter Reservoir", ["Gas sites", "Wormhole sites"], "", ("wormhole_gas", "Gas Site", 1)),
        ("Average Frontier Deposit", ["Ore sites", "Wormhole sites"], "", ("wormhole_ore", "Ore Anomaly", 0)),
        ("Bandit Nebula", ["Gas sites"], "cytoserocin", ("gas", "Gas Site", 1)),
        ("Serpentis Chemical Lab", ["Chemical Labs"], "chemical", ("chemical_lab", "Gas Site", 1)),
        ("Limited Sleeper Cache", ["Data sites"], "", ("sleeper_cache", "Data Site", 1)),
        ("Hidden Gneiss Deposit", ["Ore sites"], "", ("ore", "Ore Site", 1)),
        ("Large Gneiss Deposit", ["Ore sites"], "", ("ore", "Ore Anomaly", 0)),
        ("Blue Ice Belt", ["Ice belts"], "", ("ice", "Ice Anomaly", 0)),
        ("Raid", ["Homefront Operations"], "", ("homefront", "Combat Anomaly", 0)),
        ("Nation Mining Colony", ["Incursions sites"], "", ("incursion", "Combat Anomaly", 0)),
        ("Torpid Sleeper Hive", ["PvE"], "anomaly", ("pochven", "Combat Anomaly", 0)),
        ("Overmind Nursery Grove", ["Data sites"], "Data Site", ("pochven", "Combat Site", 1)),
        ("Rampant Drone Fabricator", ["Game events"], "signature", ("wormhole_combat", "Combat Site", 1)),
        ("Epicenter", ["Wormhole sites"], "", ("wormhole_combat", "Beacon", 0)),
        ("Unknown Anomaly", ["Wormhole sites"], "", ("drifter", "Beacon", 0)),
        ("Drone Horde", ["Combat Anomalies"], "anomaly", ("combat_anomaly", "Combat Anomaly", 0)),
    ],
)
def test_classify(title, cats, itype, expected):
    assert rules.classify(page(title, cats, {"type": itype} if itype else {})) == expected


# --------------------------------------------------------------------------- aggregate_enemies
def test_aggregate_sums_waves_and_pluralises():
    rows = [row("frigate", 1, 2), row("frigate", 1, 3, wave="Wave 2"), row("cruiser", 1, 1), row("battleship", 1, 1, tier="commander"),
            row("sentry", 10, 10)]
    summary, ewar, enemy_rows = rules.aggregate_enemies(rows)
    assert summary == "2-5 frigates, 1 cruiser, 1 battleship, 10 sentries (incl. commander/overseer)"
    assert ewar is None
    assert len(enemy_rows) == 5


def test_aggregate_unknown_counts_and_ewar_and_sleeper_prefix():
    rows = [row("frigate", None, None, ewar=["Web"]), row("cruiser", 1, 2, ewar=["scram", "Energy Neutralization"])]
    summary, ewar, _ = rules.aggregate_enemies(rows, faction="Sleepers")
    assert summary == "some Sleeper frigates, 1-2 Sleeper cruisers"
    assert ewar == "web, scram, neut"


def test_aggregate_skips_non_hostile_and_structures():
    rows = [row("frigate", 2, 2, hostile=False), row("cruiser", 3, 3)]
    summary, _, enemy_rows = rules.aggregate_enemies(rows)
    assert summary == "3 cruisers"
    assert len(enemy_rows) == 1


def test_aggregate_variant_dedupe_keeps_largest():
    rows = [row("frigate", 4, 4, section="Highsec variant"), row("battleship", 2, 2, section="Lowsec variant")]
    summary, _, _ = rules.aggregate_enemies(rows)
    assert summary == "2 battleships (per variant)"


def test_aggregate_none_when_no_rows():
    assert rules.aggregate_enemies([], combat=False)[0] == "None"
    assert rules.aggregate_enemies([], combat=True)[0] == "Unknown"


def test_aggregate_zero_dash_question_counts_are_unknown():
    rows = [row("frigate", 0, 0), row("dreadnought", 4, 4)]
    assert rules.aggregate_enemies(rows)[0] == "some frigates, 4 dreadnoughts"


def test_aggregate_collapses_alternate_pockets():
    rows = [row("battleship", 8, 12, section="1st Pocket"),
            row("battleship", 7, 10, section="3rd Pocket (Supply Depot)"),
            row("battleship", 11, 11, section="3rd Pocket (Watchpost)"),
            row("destroyer", 10, 10, section="3rd Pocket (Watchpost)")]
    summary, _, _ = rules.aggregate_enemies(rows)
    assert summary == "10 destroyers, 19-23 battleships (per variant)"


def test_enemies_fallback():
    assert "Vanguard" in rules.enemies_fallback("Nation Mining Colony", "incursion").lower().title()
    assert rules.enemies_fallback("Minor Conduit", "pochven").startswith("5 waves")
    assert rules.enemies_fallback("Angel Hideaway", "combat_anomaly") is None


# --------------------------------------------------------------------------- danger / min ship
@pytest.mark.parametrize("rating, expected", [("1/10", 2), ("3/10", 2), ("4/10", 3), ("6/10", 3), ("7/10", 4), ("8/10", 4), ("10/10", 5)])
def test_danger_ded_boundaries(rating, expected):
    p = page("X", ["DED Complexes"], {"type": "ded", "rating": rating})
    assert rules.danger_of(p, "combat_ded", "Null") == expected


@pytest.mark.parametrize("title, expected", [("Angel Hideaway", 2), ("Angel Refuge", 2), ("Angel Den", 3), ("Angel Rally Point", 3),
                                             ("Angel Port", 4), ("Angel Haven", 4), ("Angel Sanctum", 5), ("Serpentis Forsaken Sanctum", 5),
                                             ("Drone Horde", 5), ("Drone Cluster", 2)])
def test_danger_anomaly_tiers(title, expected):
    assert rules.danger_of(page(title, ["Combat Anomalies"]), "combat_anomaly", "Null") == expected


def test_danger_bumps_when_battleships_present():
    p = page("Angel Hideaway", ["Combat Anomalies"], rows=[row("battleship", 1, 1)])
    assert rules.danger_of(p, "combat_anomaly", "High") == 3


@pytest.mark.parametrize("space, expected", [("C1", 3), ("C2", 3), ("C3", 4), ("C4", 4), ("C5", 5), ("C6", 5)])
def test_danger_wormhole_classes(space, expected):
    assert rules.danger_of(page("Some Site"), "wormhole_combat", space) == expected


def test_min_ship_respects_gate_limit():
    p = page("Serpentis Narcotic Warehouses", ["DED Complexes"], {"type": "ded", "rating": "3/10", "ship limit": "Cruisers"})
    assert "cruiser" in rules.min_ship_of(p, "combat_ded", "High", 2).lower()
    p2 = page("Angel Vigil", ["Unrated Complexes"], {"type": "unrated", "ship limit": "Battlecruiser"})
    assert rules.min_ship_of(p2, "combat_unrated", "High", 3).startswith("Battlecruiser")
    p3 = page("Angel Hideout", ["Unrated Complexes"], {"type": "unrated", "ship limit": "Destroyer"})
    assert rules.min_ship_of(p3, "combat_unrated", "High", 2) == "Destroyer"
    # A frigate-only gate caps a battleship recommendation down to the frigate phrase.
    assert rules.cap_by_limit("Battleship / T3C", "Frigate") == "T1 frigate"
    assert rules.cap_by_limit("Battleship / T3C", "Unrestricted") == "Battleship / T3C"


def test_space_and_rating_helpers():
    assert rules.normalise_space("High, Low, Null") == "High, Low, Null"
    assert rules.normalise_space("C5 Wormholes") == "C5"
    assert rules.normalise_space("[[Pochven]]") == "Pochven"
    assert rules.space_of(page("Forgotten Perimeter Gateway", ["Wormhole sites"]), "wormhole_relic") == "C2"
    assert rules.space_of(page("Vital Core Reservoir", ["Gas sites", "Wormhole sites"]), "wormhole_gas") == "C5-C6"
    assert rules.space_of(page("Angel Forlorn Den", ["Combat Anomalies"]), "combat_anomaly") == "Low, Null"
    assert rules.rating_of(page("Angel Forlorn Den"), "combat_anomaly") == "Tier 4 Level 4"
    assert rules.rating_of(page("X", ["DED Complexes"], {"rating": "DED 4/10"}), "combat_ded") == "4/10"
    assert rules.faction_of(page("Gurista Outpost", [], {"faction": "Guristas"})) == "Guristas"
    assert rules.faction_of(page("Core Garrison", ["Wormhole sites"])) == "Sleepers"


# --------------------------------------------------------------------------- integration
@pytest.fixture(scope="module")
def catalog(tmp_path_factory) -> sqlite3.Connection:
    if not PARSED_FILE.exists():
        pytest.skip("data/parsed_sites.json missing; run uv run python -m scraper.parse")
    out = tmp_path_factory.mktemp("db") / "catalog.sqlite"
    build.build(out)
    conn = sqlite3.connect(out)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


def _site(conn, name, space=None):
    q = "SELECT * FROM sites WHERE name = ?" + (" AND space = ?" if space else "")
    rows = conn.execute(q, (name, space) if space else (name,)).fetchall()
    assert rows, f"{name} missing"
    return rows[0]


def test_catalog_size_and_integrity(catalog):
    total = catalog.execute("SELECT COUNT(*) FROM sites").fetchone()[0]
    assert total >= 900
    assert catalog.execute("SELECT COUNT(*) FROM sites WHERE enemies = '' OR min_ship = '' OR space = ''").fetchone()[0] == 0
    labels = {0: "n/a", 1: "Safe", 2: "Low", 3: "Medium", 4: "High", 5: "Deadly"}
    for r in catalog.execute("SELECT danger, danger_label FROM sites"):
        assert labels[r["danger"]] == r["danger_label"]
    assert catalog.execute("SELECT COUNT(*) FROM (SELECT name, space FROM sites GROUP BY name, space HAVING COUNT(*) > 1)").fetchone()[0] == 0
    meta = dict(catalog.execute("SELECT key, value FROM meta").fetchall())
    assert int(meta["site_count"]) == total


def test_catalog_spot_checks(catalog):
    s = _site(catalog, "Serpentis Narcotic Warehouses")
    assert s["category"] == "combat_ded" and s["rating"] == "3/10" and s["danger"] == 2
    assert "cruiser" in s["min_ship"].lower() and "frigates" in s["enemies"]

    s = _site(catalog, "Forgotten Perimeter Gateway")
    assert s["category"] == "wormhole_relic" and s["space"] == "C2" and s["danger"] == 3
    assert "Sleeper cruisers" in s["enemies"] and "Sleeper battleships" in s["enemies"]

    s = _site(catalog, "Local Serpentis Mainframe")
    assert s["category"] == "data" and s["space"] == "High" and s["danger"] == 1 and s["danger_label"] == "Safe"
    assert s["enemies"] == "None"

    s = _site(catalog, "Lesser Guristas Covert Research Facility")
    assert s["category"] == "ghost" and s["space"] == "High"

    s = _site(catalog, "Wormhole K162")
    assert s["category"] == "wormhole_connection" and s["danger"] == 0

    assert _site(catalog, "Angel Sanctum")["danger"] == 5

    s = _site(catalog, "Barren Perimeter Reservoir")
    assert s["category"] == "wormhole_gas" and s["min_ship"].startswith("Venture")

    assert _site(catalog, "Quarantine Area")["space"] == "C5"
    assert catalog.execute("SELECT COUNT(*) FROM sites WHERE name LIKE '%(updated)'").fetchone()[0] == 0
    assert _site(catalog, "Barbican")["category"] == "drifter"
    assert _site(catalog, "Guristas Stronghold")["danger"] == 5
    assert catalog.execute("SELECT COUNT(*) FROM site_enemies").fetchone()[0] > 3000
