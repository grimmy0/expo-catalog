"""Unit tests for scraper.rules and an integration test for scraper.build."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

from scraper import build, curated, rules
from scraper.parse import PARSED_FILE

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def page(
    title: str,
    categories: list[str] | None = None,
    infobox: dict | None = None,
    rows: list[dict] | None = None,
    flags: dict | None = None,
) -> dict:
    return {
        "title": title,
        "categories": categories or [],
        "infobox": infobox or {},
        "npc_rows": rows or [],
        "flags": flags or {},
        "escalations": [],
        "description": "",
        "blue_loot_isk": None,
    }


def row(cls: str, lo: int | None, hi: int | None, name: str = "x", **kw) -> dict:
    return {
        "section": kw.get("section"),
        "wave": kw.get("wave", "Wave 1"),
        "ship_class": cls,
        "count_min": lo,
        "count_max": hi,
        "name": name,
        "tier": kw.get("tier"),
        "hostile": kw.get("hostile", True),
        "ewar": kw.get("ewar", []),
        "trigger": None,
    }


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
    rows = [
        row("frigate", 1, 2),
        row("frigate", 1, 3, wave="Wave 2"),
        row("cruiser", 1, 1),
        row("battleship", 1, 1, tier="commander"),
        row("sentry", 10, 10),
    ]
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
    rows = [
        row("battleship", 8, 12, section="1st Pocket"),
        row("battleship", 7, 10, section="3rd Pocket (Supply Depot)"),
        row("battleship", 11, 11, section="3rd Pocket (Watchpost)"),
        row("destroyer", 10, 10, section="3rd Pocket (Watchpost)"),
    ]
    summary, _, _ = rules.aggregate_enemies(rows)
    assert summary == "10 destroyers, 19-23 battleships (per variant)"


def test_three_token_location_is_kept():
    p = page(
        "Serpentis Narcotic Warehouses",
        ["DED Complexes"],
        {"type": "ded", "rating": "3/10", "location": "High, Low, Null"},
    )
    assert rules.space_of(p, "combat_ded") == "High, Low, Null"
    assert rules.normalise_space("Null and low") == "Low, Null"


def test_guarded_gas_danger_and_ship_follow_the_aggregate():
    guarded = page(
        "Leopard Nebula",
        ["Gas sites"],
        {"type": "Cytoserocin", "is guarded": "Yes"},
        rows=[row("frigate", 8, 8), row("cruiser", 2, 2), row("battleship", 19, 19), row("sentry", 8, 8)],
    )
    assert rules.danger_of(guarded, "gas", "Null") == 4
    assert rules.min_ship_of(guarded, "gas", "Null", 4) == "Battleship to clear, then Venture"
    cruisers = page(
        "X Nebula", ["Gas sites"], {"type": "Cytoserocin", "is guarded": "Yes"}, rows=[row("cruiser", 3, 3)]
    )
    assert rules.danger_of(cruisers, "gas", "Null") == 3
    assert rules.min_ship_of(cruisers, "gas", "Null", 3) == "Cruiser to clear, then Venture"
    frigs = page("Y Nebula", ["Gas sites"], {"type": "Cytoserocin", "is guarded": "Yes"}, rows=[row("frigate", 4, 4)])
    assert rules.danger_of(frigs, "gas", "Null") == 2
    assert rules.min_ship_of(frigs, "gas", "Null", 2) == "Destroyer to clear, then Venture"
    safe = page("Z Nebula", ["Gas sites"], {"type": "Mykoserocin", "is guarded": "No"})
    assert rules.danger_of(safe, "gas", "High") == 1 and rules.min_ship_of(safe, "gas", "High", 1) == "Venture"


def test_battleship_bump_applies_to_every_category():
    p = page("Hidden Omber Deposit", ["Ore sites"], rows=[row("battleship", 1, 1)])
    assert rules.danger_of(p, "ore", "Low") == 3


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Underworld Smugglers (pirate", "Underworld Smugglers"),
        ("Guri Malakim (Guristas and Angel Cartel pirate", "Guri Malakim"),
        ("Society of Conscious Thought, EDENCOM and", "Society of Conscious Thought"),
        ("Rogue Drones (Type-A/B/C/D Anomalous variants", "Rogue Drones"),
        ("SARO (CONCORD special forces", "CONCORD/SARO"),
        ("Amarr slavers ('Irregular' NPCs", "Amarr slavers"),
        ("Blood Raiders or Sansha (Amarr), Guristas", "Blood Raiders"),
        ("Purity of the Throne (Amarr purists", "Purity of the Throne"),
        ("unknown (page body is carried over)", None),
        ("none", None),
    ],
)
def test_canonical_faction(raw, expected):
    out = rules.canonical_faction(raw)
    assert out == expected
    if out:
        assert len(out) <= 40 and not out.endswith("(")


@pytest.mark.parametrize(
    "raw, danger, expected",
    [
        ("Clearly requires a Capital ship or at least a powerful", 5, "Fleet / capital ships"),
        ("Can be completed in a destroyer tanked against", 3, "Destroyer"),
        ("Battleship or Heavy Assault Cruiser (page's general advice", 4, "Battleship / HAC"),
        ("Doable with a well fit Battlecruiser with application", 3, "Battlecruiser (Drake/Gnosis/Myrmidon)"),
        ("Class 1: basic Tech I frigate", 2, "T1 frigate"),
        ("Soloable with a challenge (patch-note quote)", 4, "Battleship / T3C"),
        ("A T1 cruiser can run the site easily", 2, "T1 cruiser (Vexor/Caracal/Omen/Rupture)"),
        ("Best run with a marauder", 5, "Marauder / Rattlesnake"),
        ("At least 3 capsuleers in T1 frigates/destroyers", 3, "Small gang (3-5)"),
        ("10+ capsuleer battleship fleet with logistics and EWAR", 5, "Fleet (10+, logi)"),
        ("Speed tanking ideal in anything smaller than a battleship", 3, "Battleship (Dominix/Rattlesnake/Praxis)"),
        ("", 1, "Any ship"),
    ],
)
def test_normalise_min_ship(raw, danger, expected):
    assert rules.normalise_min_ship(raw, danger) == expected


def test_ship_tier_and_consistency_check():
    assert rules.ship_tier("T1 explo frigate (Heron/Probe/Imicus/Magnate)") == 0
    assert rules.ship_tier("Destroyer") == 2
    assert rules.ship_tier("Battlecruiser / T3C") == 5
    assert rules.ship_tier("Marauder; 2+ pilots recommended") == 6
    bad = {
        "category": "event",
        "scan_group": "Combat Anomaly",
        "status": "event",
        "danger": 4,
        "min_ship": "T1 cruiser (Vexor/Caracal/Omen/Rupture)",
        "name": "x",
        "space": "High",
    }
    assert build.consistency_issues(bad) == "danger 4 needs battleship/T3C/gang"
    changes = build.reconcile([bad])
    assert changes and bad["min_ship"] == "Battleship / T3C"
    ok = dict(bad, danger=3)
    assert build.consistency_issues(ok) is None


def test_hazard_enemies():
    p = page("Some Cache", ["Data sites"])
    p["description"] = "Two sentry towers guard the cans and proximity mines explode when approached."
    assert rules.hazard_enemies(p) == "No ships; sentry towers, proximity mines, exploding containers"
    assert rules.hazard_enemies(page("Plain", ["Data sites"])) is None


def test_enemies_fallback():
    assert "Vanguard" in rules.enemies_fallback("Nation Mining Colony", "incursion").lower().title()
    assert rules.enemies_fallback("Minor Conduit", "pochven").startswith("5 waves")
    assert rules.enemies_fallback("Angel Hideaway", "combat_anomaly") is None


# --------------------------------------------------------------------------- danger / min ship
@pytest.mark.parametrize(
    "rating, expected", [("1/10", 2), ("3/10", 2), ("4/10", 3), ("6/10", 3), ("7/10", 4), ("8/10", 4), ("10/10", 5)]
)
def test_danger_ded_boundaries(rating, expected):
    p = page("X", ["DED Complexes"], {"type": "ded", "rating": rating})
    assert rules.danger_of(p, "combat_ded", "Null") == expected


@pytest.mark.parametrize(
    "title, expected",
    [
        ("Angel Hideaway", 2),
        ("Angel Refuge", 2),
        ("Angel Den", 3),
        ("Angel Rally Point", 3),
        ("Angel Port", 4),
        ("Angel Haven", 4),
        ("Angel Sanctum", 5),
        ("Serpentis Forsaken Sanctum", 5),
        ("Drone Horde", 5),
        ("Drone Cluster", 2),
    ],
)
def test_danger_anomaly_tiers(title, expected):
    assert rules.danger_of(page(title, ["Combat Anomalies"]), "combat_anomaly", "Null") == expected


def test_danger_bumps_when_battleships_present():
    p = page("Angel Hideaway", ["Combat Anomalies"], rows=[row("battleship", 1, 1)])
    assert rules.danger_of(p, "combat_anomaly", "High") == 3


@pytest.mark.parametrize("space, expected", [("C1", 3), ("C2", 3), ("C3", 4), ("C4", 4), ("C5", 5), ("C6", 5)])
def test_danger_wormhole_classes(space, expected):
    assert rules.danger_of(page("Some Site"), "wormhole_combat", space) == expected


def test_min_ship_respects_gate_limit():
    p = page(
        "Serpentis Narcotic Warehouses", ["DED Complexes"], {"type": "ded", "rating": "3/10", "ship limit": "Cruisers"}
    )
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


# --------------------------------------------------------------------------- COSMOS sites
def cosmos(title="Some COSMOS Site", infobox=None, rows=None, hint=None, system=None, cats=None) -> dict:
    p = page(title, cats or ["COSMOS sites"], infobox, rows)
    p.update(scan_hint=hint, system=system)
    return p


@pytest.mark.parametrize(
    ("p", "expected"),
    [
        (cosmos(hint="signature"), ("cosmos", "Combat Site", 1)),
        (cosmos(hint="beacon"), ("cosmos", "Beacon", 0)),
        (cosmos(hint="anomaly"), ("cosmos", "Combat Anomaly", 0)),
        (cosmos(hint=None), ("cosmos", "Beacon", 0)),  # unsaid: COSMOS complexes are mostly beacons
        # The COSMOS category beats the infobox type (Yan Jung Relic Site says type=ded).
        (cosmos("Yan Jung Relic Site", {"type": "ded"}, hint="beacon"), ("cosmos", "Beacon", 0)),
        (cosmos("Guristas Guard Post", {"type": "unrated"}, hint="signature"), ("cosmos", "Combat Site", 1)),
        # COSMOS gas nebulae stay gas sites.
        (cosmos("Icy Nebula", {"type": "COSMOS"}, cats=["COSMOS sites", "Gas sites"]), ("gas", "Gas Site", 1)),
        # No COSMOS category: type=cosmos is still the gas-nebula marker.
        (page("Polar Bear Nebula", ["Gas sites"], {"type": "COSMOS"}), ("gas", "Gas Site", 1)),
        # Pages that lost their topic category, found through the infobox template.
        (
            page("Khanid Stronghold", [], {"location": "High", "faction": "Khanid"}),
            ("combat_unrated", "Combat Site", 1),
        ),
        (page("Accelerator Flashpoint", ["Needing updates"], {"type": "anomaly"}), ("pochven", "Combat Anomaly", 0)),
        (page("Nation Industrial Proxy", ["Incursions sites"]), ("incursion", "Combat Anomaly", 0)),
    ],
)
def test_classify_cosmos_and_rediscovered_pages(p, expected):
    assert rules.classify(p) == expected


def test_cosmos_space():
    ppg = {"name": "PPG-XC", "security": -0.0436, "region": "Cloud Ring"}
    assert rules.space_of(cosmos(system=ppg), "cosmos") == "Null (PPG-XC, Cloud Ring)"
    # Unresolved system: fall back to the security the page shows, then to the band it names.
    rated = cosmos(infobox={"location": "Thelan ({{ColorSecurityRating|-0.2}}) - Sinq Laison"})
    assert rules.space_of(rated, "cosmos") == "Null"
    assert rules.space_of(cosmos(infobox={"location": "High"}), "cosmos") == "High"
    assert rules.space_of(cosmos(infobox={"location": "?"}), "cosmos") == "Unknown"


def test_cosmos_faction_prefers_the_infobox_then_the_npc_majority():
    assert rules.faction_of(cosmos(infobox={"faction": "Maru Pirates"}, rows=[row("cruiser", 9, 9, "Corpum")])) == (
        "Maru Pirates"
    )
    bandits = [row("frigate", 9, 9, "Caldari Drifter"), row("frigate", 1, 1, "Caldari Bandit")]
    assert rules.faction_of(cosmos(rows=bandits)) == "Caldari State"  # COSMOS "Drifter" bandits, not the Drifters
    serp = [row("battleship", 5, 5, "Core Lord Admiral"), row("cruiser", 3, 3, "Corelum Chief Infantry")]
    assert rules.faction_of(cosmos(infobox={"faction": "Serpentis"}, rows=serp)) == "Serpentis"
    assert rules.faction_of(cosmos(rows=[row("frigate", 3, 3, "Kazka Bandit")])) == "Kazka Bandits"
    assert rules.faction_of(cosmos()) is None


def test_cosmos_rating_danger_and_min_ship():
    courier = cosmos(
        "Courier Gone Missing (2 of 2)",
        {"level": "4", "faction": "Serpentis"},
        [row("battleship", 5, 5, "Core Lord Admiral"), row("cruiser", 3, 3, "Corelum Chief Sentinel")],
        hint="signature",
    )
    assert rules.rating_of(courier, "cosmos") == "COSMOS L4"
    assert rules.rating_of(cosmos(), "cosmos") == "COSMOS"
    assert rules.danger_of(courier, "cosmos", "Null") == 4
    assert rules.min_ship_of(courier, "cosmos", "Null", 4) == "Battleship / T3C"
    frigs = cosmos(rows=[row("frigate", 9, 9, "Guristas Despoiler")])
    assert (
        rules.danger_of(frigs, "cosmos", "High") == 2 and rules.min_ship_of(frigs, "cosmos", "High", 2) == "Destroyer"
    )
    bc = cosmos(rows=[row("battlecruiser", 3, 3, "x")], infobox={"ship limit": "Cruiser"})
    assert rules.danger_of(bc, "cosmos", "High") == 3
    assert rules.min_ship_of(bc, "cosmos", "High", 3) == "T1 cruiser (Vexor/Caracal/Omen/Rupture)"  # gate cap
    dread = cosmos(rows=[row("dreadnought", 1, 1, "x")])
    assert rules.danger_of(dread, "cosmos", "Null") == 5
    unknown = cosmos()
    assert (
        rules.danger_of(unknown, "cosmos", "High") == 0 and rules.min_ship_of(unknown, "cosmos", "High", 0) == "Unknown"
    )
    neutral = cosmos(rows=[row("frigate", 3, 3, "PD Security Enforcer", hostile=False)])
    assert rules.danger_of(neutral, "cosmos", "High") == 1


def test_cosmos_page_record():
    neutral = cosmos(
        "Pend Insurance Storage Bin",
        {"signature strength": "Beacon"},
        [row("frigate", 3, 3, "PD Security Enforcer", hostile=False)],
        hint="beacon",
        system={"name": "Fluekele", "security": 0.6, "region": "Sinq Laison"},
    )
    rec = build.page_record(neutral)
    assert rec["category"] == "cosmos" and rec["scan_group"] == "Beacon" and rec["is_signature"] == 0
    assert rec["space"] == "High (Fluekele, Sinq Laison)"
    assert rec["enemies"] == "None (neutral NPCs only)" and rec["danger"] == 1
    assert rec["loot_note"] is None  # "Beacon" is not a signature strength
    sig = cosmos("Gatti Zhara", {"signature strength": "5% in High Sec"}, [row("frigate", 3, 3, "x")], hint="signature")
    assert build.page_record(sig)["loot_note"] == "Signature strength 5% in High Sec"


def test_rediscovered_pages_rules():
    flash = page("Accelerator Flashpoint", ["Needing updates"], {"type": "anomaly", "faction": "Triglavians"})
    assert rules.space_of(flash, "pochven") == "High, Low (EDENCOM fortress systems)"
    assert rules.status_of(flash, "pochven") == "active"
    assert rules.danger_of(flash, "pochven", "") == 5
    assert rules.faction_of(flash) == "Triglavian Collective"
    khanid = page("Khanid Stronghold", [], {"location": "High", "faction": "Khanid"}, [row("cruiser", 12, 12, "x")])
    assert rules.space_of(khanid, "combat_unrated") == "High (Amarr space)"
    assert rules.danger_of(khanid, "combat_unrated", "High") == 3
    assert rules.faction_of(khanid) == "Khanid Kingdom"
    proxy = page("Nation Industrial Proxy", ["Incursions sites"])
    assert rules.rating_of(proxy, "incursion") == "Staging"
    assert rules.min_ship_of(proxy, "incursion", "", rules.danger_of(proxy, "incursion", "")) == "Frigate gang (3+)"


# --------------------------------------------------------------------------- event data
def test_event_file_exists_and_loads():
    assert curated.EVENTS_FILE.is_file()
    events = curated.load_events()
    assert events and all(e.get("name") for e in events)
    assert curated.event_sites(events)


def test_missing_event_file_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(curated, "EVENTS_FILE", tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError, match="missing.json"):
        curated.load_events()
    # Passing events explicitly never touches the file.
    assert curated.generated_sites({}, events=[]) is not None


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
    assert (
        catalog.execute("SELECT COUNT(*) FROM sites WHERE enemies = '' OR min_ship = '' OR space = ''").fetchone()[0]
        == 0
    )
    labels = {0: "n/a", 1: "Safe", 2: "Low", 3: "Medium", 4: "High", 5: "Deadly"}
    for r in catalog.execute("SELECT danger, danger_label FROM sites"):
        assert labels[r["danger"]] == r["danger_label"]
    assert (
        catalog.execute(
            "SELECT COUNT(*) FROM (SELECT name, space FROM sites GROUP BY name, space HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        == 0
    )
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
    assert _site(catalog, "Serpentis Narcotic Warehouses")["space"] == "High, Low, Null"
    s = _site(catalog, "Leopard Nebula")
    assert s["danger"] == 4 and s["min_ship"] == "Battleship to clear, then Venture"
    assert _site(catalog, "Limited Sleeper Cache")["enemies"].startswith("No ships")
    assert _site(catalog, "Observatory Infiltration")["enemies"].startswith("8 Patient Eradicator")
    assert _site(catalog, "Observatory Flashpoint")["enemies"].startswith("Waves of EDENCOM")
    assert _site(catalog, "Deepflow Rift")["enemies"].startswith("Surge of")
    cg = _site(catalog, "Crimson Gauntlet")
    assert cg["danger"] == 3 and cg["min_ship"].startswith("Battlecruiser")
    mc = _site(catalog, "Minor Conduit")
    assert mc["status"] == "active" and mc["space"] == "Triglavian/EDENCOM minor-victory systems; Pochven"
    assert _site(catalog, "Emerging Conduit")["status"] == "active"
    assert _site(catalog, "Emerging Conduit (2019-2020 highsec version)")["status"] == "removed"
    assert _site(catalog, "Wormhole K162")["rating"] == "K162 (exit)"
    assert _site(catalog, "Wormhole B274")["rating"] == "→ High-sec"


def test_catalog_includes_cosmos_and_rediscovered_sites(catalog):
    s = _site(catalog, "Courier Gone Missing (2 of 2)")
    assert s["category"] == "cosmos" and s["scan_group"] == "Combat Site" and s["is_signature"] == 1
    assert s["space"] == "Null (PPG-XC, Cloud Ring)" and s["rating"] == "COSMOS L4"
    assert s["faction"] == "Serpentis" and s["danger"] == 4 and "battleships" in s["enemies"]
    assert s["source_url"] == "https://wiki.eveuniversity.org/Courier_Gone_Missing_(2_of_2)"
    assert catalog.execute("SELECT COUNT(*) FROM sites WHERE category = 'cosmos'").fetchone()[0] >= 80
    assert _site(catalog, "Maru Prison Facility")["space"] == "High (Hjoramold, Metropolis)"
    assert _site(catalog, "Contested Minmatar Military Depot")["scan_group"] == "Beacon"
    assert _site(catalog, "Yan Jung Relic Site")["category"] == "cosmos"
    for gas in ("Icy Nebula", "Polar Bear Nebula"):  # COSMOS gas nebulae stay gas sites
        assert _site(catalog, gas)["category"] == "gas"
    assert _site(catalog, "Nation Industrial Proxy")["rating"] == "Staging"
    assert _site(catalog, "Khanid Stronghold")["category"] == "combat_unrated"
    assert _site(catalog, "Blood Annex")["category"] == "combat_unrated"
    assert _site(catalog, "Accelerator Flashpoint")["status"] == "active"
    # Escalation destinations and Mercenary Den sites are not catalogued.
    for name in ("Angel Capital Staging", "Molting Season", "Drifter Muster Point"):
        assert catalog.execute("SELECT COUNT(*) FROM sites WHERE name = ?", (name,)).fetchone()[0] == 0


def test_catalog_vocabularies(catalog):
    sentence = ("is ", "can ", " be ", "with a", "ideal", "requires", "recommendation", "quote", "doable", "advice")
    for r in catalog.execute("SELECT name, min_ship, faction FROM sites"):
        low = r["min_ship"].lower()
        assert len(r["min_ship"]) <= 70, (r["name"], r["min_ship"])
        assert not any(w in low for w in sentence), (r["name"], r["min_ship"])
        if r["faction"]:
            assert len(r["faction"]) <= 40 and not r["faction"].endswith("("), (r["name"], r["faction"])
    for r in catalog.execute("SELECT * FROM sites"):
        assert build.consistency_issues(dict(r)) is None, (r["name"], r["danger"], r["min_ship"])
    assert catalog.execute("SELECT COUNT(*) FROM sites WHERE name LIKE '%(updated)'").fetchone()[0] == 0
    assert _site(catalog, "Barbican")["category"] == "drifter"
    assert _site(catalog, "Guristas Stronghold")["danger"] == 5
    assert catalog.execute("SELECT COUNT(*) FROM site_enemies").fetchone()[0] > 3000
