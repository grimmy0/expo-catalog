"""Derive catalog fields (category, space, faction, enemies, danger, min ship) from parsed pages.

Everything here is a pure function over the ``ParsedPage`` dicts produced by
``scraper.parse`` (see ``data/parsed_sites.json``). Hand-curated additions and
overrides live in ``scraper.curated``; the SQLite build is ``scraper.build``.

Danger scale (``DANGER_LABELS``):
    0 n/a     no NPC threat of its own (wormhole connections, unknown)
    1 Safe    no hostile NPCs
    2 Low     a T1 frigate / destroyer handles it
    3 Medium  cruiser / battlecruiser needed
    4 High    battleship / T3C / Marauder or a small gang
    5 Deadly  fleet-only or capital-class threat
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

DANGER_LABELS: dict[int, str] = {0: "n/a", 1: "Safe", 2: "Low", 3: "Medium", 4: "High", 5: "Deadly"}

CLASS_ORDER: tuple[str, ...] = (
    "frigate",
    "destroyer",
    "cruiser",
    "battlecruiser",
    "battleship",
    "dreadnought",
    "carrier",
    "supercarrier",
    "titan",
    "fighter",
    "drone",
    "sentry",
)
_PLURAL = {"sentry": "sentries"}

# Ship-size ladder used to cap recommendations by acceleration-gate limits.
SIZE_LADDER: tuple[str, ...] = ("frigate", "destroyer", "cruiser", "battlecruiser", "battleship")
SHIP_PHRASES: dict[str, str] = {
    "frigate": "T1 frigate",
    "destroyer": "Destroyer",
    "cruiser": "T1 cruiser (Vexor/Caracal/Omen/Rupture)",
    "battlecruiser": "Battlecruiser (Drake/Gnosis/Myrmidon)",
    "battleship": "Battleship / T3C",
}

PIRATE_FACTIONS = ("Angel", "Blood", "Guristas", "Gurista", "Sansha", "Serpentis")

# --------------------------------------------------------------------------- wormhole site lists
WH_ANOMALIES: dict[str, str] = {
    "Perimeter Ambush Point": "C1",
    "Perimeter Camp": "C1",
    "Phase Catalyst Node": "C1",
    "The Line": "C1",
    "Perimeter Checkpoint": "C2",
    "Perimeter Hangar": "C2",
    "The Ruins of Enclave Cohort 27": "C2",
    "Sleeper Data Sanctuary": "C2",
    "Fortification Frontier Stronghold": "C3",
    "Outpost Frontier Stronghold": "C3",
    "Solar Cell": "C3",
    "The Oruze Construct": "C3",
    "Frontier Barracks": "C4",
    "Frontier Command Post": "C4",
    "Integrated Terminus": "C4",
    "Sleeper Information Sanctum": "C4",
    "Core Garrison": "C5",
    "Core Stronghold": "C5",
    "Oruze Osobnyk": "C5",
    "Quarantine Area": "C5",
    "Core Citadel": "C6",
    "Core Bastion": "C6",
    "Strange Energy Readings": "C6",
    "The Mirror": "C6",
}
WH_DATA: dict[str, str] = {
    "Unsecured Perimeter Amplifier": "C1",
    "Unsecured Perimeter Information Center": "C1",
    "Unsecured Perimeter Comms Relay": "C2",
    "Unsecured Perimeter Transponder Farm": "C2",
    "Unsecured Frontier Database": "C3",
    "Unsecured Frontier Receiver": "C3",
    "Unsecured Frontier Digital Nexus": "C4",
    "Unsecured Frontier Trinary Hub": "C4",
    "Unsecured Frontier Enclave Relay": "C5",
    "Unsecured Frontier Server Bank": "C5",
    "Unsecured Core Backup Array": "C6",
    "Unsecured Core Emergence": "C6",
}
WH_RELIC: dict[str, str] = {
    "Forgotten Perimeter Coronation Platform": "C1",
    "Forgotten Perimeter Power Array": "C1",
    "Forgotten Perimeter Gateway": "C2",
    "Forgotten Perimeter Habitation Coils": "C2",
    "Forgotten Frontier Quarantine Outpost": "C3",
    "Forgotten Frontier Recursive Depot": "C3",
    "Forgotten Frontier Conversion Module": "C4",
    "Forgotten Frontier Evacuation Center": "C4",
    "Forgotten Core Data Field": "C5",
    "Forgotten Core Information Pen": "C5",
    "Forgotten Core Assembly Hall": "C6",
    "Forgotten Core Circuitry Disassembler": "C6",
}
WH_GAS: dict[str, str] = {
    "Barren Perimeter Reservoir": "C1-C4",
    "Minor Perimeter Reservoir": "C1-C4",
    "Ordinary Perimeter Reservoir": "C1-C4",
    "Sizeable Perimeter Reservoir": "C1-C4",
    "Sizable Perimeter Reservoir": "C1-C4",
    "Token Perimeter Reservoir": "C1-C4",
    "Bountiful Frontier Reservoir": "C3-C6",
    "Vast Frontier Reservoir": "C3-C6",
    "Instrumental Core Reservoir": "C5-C6",
    "Vital Core Reservoir": "C5-C6",
}
WH_ORE: dict[str, str] = {
    "Common Perimeter Deposit": "C1-C6",
    "Ordinary Perimeter Deposit": "C1-C6",
    "Average Frontier Deposit": "C1-C6",
    "Unexceptional Frontier Deposit": "C1-C6",
    "Exceptional Core Deposit": "C5-C6",
    "Infrequent Core Deposit": "C5-C6",
    "Isolated Core Deposit": "C5-C6",
    "Rarified Core Deposit": "C5-C6",
    "Uncommon Core Deposit": "C5-C6",
    "Unusual Core Deposit": "C5-C6",
    "Shattered Debris Field": "Shattered",
}

# --------------------------------------------------------------------------- combat anomaly tiers
ANOMALY_TIERS: dict[str, int] = {
    "Hideaway": 1,
    "Burrow": 2,
    "Refuge": 3,
    "Den": 4,
    "Yard": 5,
    "Rally Point": 6,
    "Port": 7,
    "Hub": 8,
    "Haven": 9,
    "Sanctum": 10,
}
DRONE_TIERS: dict[str, int] = {
    "Drone Cluster": 1,
    "Drone Collection": 2,
    "Drone Assembly": 3,
    "Drone Gathering": 4,
    "Drone Surveillance": 5,
    "Drone Menagerie": 6,
    "Drone Herd": 7,
    "Drone Squad": 8,
    "Drone Patrol": 9,
    "Drone Horde": 10,
    "Teeming Drone Horde": 10,
}
# Where each anomaly tier spawns (from the "Combat site" overview table).
ANOMALY_SPACE: dict[int, str] = {
    1: "High, Low",
    2: "High",
    3: "High, Low",
    4: "High, Low",
    5: "Low",
    6: "Low, Null",
    7: "Low, Null",
    8: "Low, Null",
    9: "Null",
    10: "Null",
}
ANOMALY_VARIANT_SPACE = {4: "Low, Null"}  # Hidden/Forsaken/Forlorn Dens are low/null only

_ANOM_RE = re.compile(
    r"^(?P<faction>Angel|Blood Raider|Blood|Guristas|Gurista|Sansha's|Sansha|Serpentis)\s+"
    r"(?P<variant>Hidden |Forsaken |Forlorn )?(?P<base>Hideaway|Burrow|Refuge|Den|Yard|Rally "
    r"Point|Port|Hub|Haven|Sanctum)$"
)

# Unrated complex ladder: name suffix -> (space, danger, min-ship phrase)
UNRATED_RULES: list[tuple[re.Pattern[str], str, int, str]] = [
    (re.compile(r" Hideout$"), "High, Low", 2, "Destroyer"),
    (re.compile(r" Lookout$"), "High, Low", 3, "T1 cruiser (Vexor/Caracal/Omen/Rupture)"),
    (re.compile(r" Watch$"), "High, Low", 3, "Battlecruiser (Drake/Gnosis/Myrmidon)"),
    (re.compile(r" Vigil$"), "High, Low", 3, "Battlecruiser (Drake/Gnosis/Myrmidon)"),
    (re.compile(r"^Provisional .* Outpost$"), "Low", 3, "Battlecruiser (Drake/Gnosis/Myrmidon)"),
    (re.compile(r" Outpost$"), "Low", 3, "Battlecruiser / Battleship"),
    (re.compile(r"^Minor .* Annex$"), "Low", 3, "Battleship / T3C"),
    (re.compile(r" Annex$"), "Low", 4, "Battleship / T3C"),
    (re.compile(r" Base$"), "Null", 4, "Battleship (Dominix/Rattlesnake/Praxis)"),
    (re.compile(r" Fortress$"), "Null", 4, "Battleship (Dominix/Rattlesnake/Praxis)"),
    (re.compile(r" Military Complex$"), "Null", 4, "Marauder / Rattlesnake"),
    (re.compile(r" Provincial HQ$"), "Null", 4, "Marauder / Rattlesnake"),
    (re.compile(r" Fleet Staging Point$"), "Null", 5, "Marauder; 2+ pilots recommended"),
    (re.compile(r"^Blood Raider Temple Complex$"), "Null", 5, "Fleet (5+, logi)"),
    # Rogue drone unrated complexes
    (
        re.compile(r"^(Haunted Yard|Desolate Site|Chemical Yard)$"),
        "High, Low",
        3,
        "T1 cruiser (Vexor/Caracal/Omen/Rupture)",
    ),
    (re.compile(r"^(Rogue Trial Yard|Dirty Site|Ruins)$"), "Low", 3, "Battlecruiser (Drake/Gnosis/Myrmidon)"),
    (re.compile(r"^(Independence|Radiance|Hierarchy)$"), "Null", 4, "Battleship (Dominix/Rattlesnake/Praxis)"),
    (
        re.compile(r"^Federation Detention Facility$"),
        "High (Aokinen constellation)",
        3,
        "Battlecruiser (Drake/Gnosis/Myrmidon)",
    ),
    (
        re.compile(r"^ISHAEKA Tactical Response HQ$"),
        "High (Monalaz constellation, Genesis)",
        4,
        "Battleship (Dominix/Rattlesnake/Praxis)",
    ),
]

COMBAT_RELIC_RUINS = (
    "Ancient Ruins",
    "Bloated Ruins",
    "Festering Ruins",
    "Forgotten Ruins",
    "Hidden Ruins",
    "Wispy Ruins",
)

INCURSION_TIERS: dict[str, tuple[str, int, str, str]] = {
    # title -> (tier, danger, min ship, pilots note)
    "Distress Beacon": ("Staging", 3, "Frigate gang (3+)", "top 5 contributors paid"),
    "Forward Reconnaissance Outpost": ("Staging", 3, "Frigate gang (3+)", "top 5 contributors paid"),
    "Propaganda Cluster": ("Staging", 3, "Frigate gang (3+)", "top 5 contributors paid"),
    "Nation Commander Outpost": ("Vanguard", 4, "Fleet (5-10, logi)", "5-10 pilots (high), 5-15 (low/null)"),
    "Nation Mining Colony": ("Vanguard", 4, "Fleet (5-10, logi)", "5-10 pilots; requires Lyavite"),
    "Override Transfer Array": ("Vanguard", 4, "Fleet (5-10, logi)", "5-10 pilots; hacker recommended"),
    "Nation Commander Stronghold": ("Assault", 5, "Fleet (10-20, logi)", "up to 20 (high) / 30 (low/null) pilots"),
    "Nation Consolidation Network": ("Assault", 5, "Fleet (10-20, logi)", "up to 20 (high) / 30 (low/null) pilots"),
    "Overwhelmed Civilian Facility": ("Assault", 5, "Fleet (10-20, logi)", "up to 20 (high) / 30 (low/null) pilots"),
    "Nation Rebirth Facility": ("Headquarters", 5, "Fleet (20-40, logi)", "20-40 (high) / 20-60 (low/null) pilots"),
    "True Creations Research Center": (
        "Headquarters",
        5,
        "Fleet (20-40, logi)",
        "20-40 (high) / 20-60 (low/null) pilots",
    ),
    "True Power Provisional Headquarters": (
        "Headquarters",
        5,
        "Fleet (20-40, logi)",
        "20-40 (high) / 20-60 (low/null) pilots",
    ),
    "The Kundalini Manifest": ("Mothership", 5, "Fleet (40-80)", "40-80 (high) / 40-120 (null) pilots; High/Null only"),
    "Uroborus": ("Mothership", 5, "Fleet (40-80)", "40-120 pilots; lowsec only"),
}

POCHVEN_TITLES: dict[str, tuple[int, str, str]] = {
    # title -> (danger, min ship, scan_group)
    "Incipient Drone Swarm": (3, "Smartbomb battleship / sniper BS", "Combat Anomaly"),
    "Convocation Watchpost": (3, "Battleship (Praxis) solo or cruiser gang", "Combat Anomaly"),
    "EDENCOM Scout Fleet": (4, "Battleship or small gang (3+)", "Combat Anomaly"),
    "Torpid Sleeper Hive": (5, "Fleet (5+, logi) or heavily tanked Marauder", "Combat Anomaly"),
    "World Ark Assault Flashpoint": (5, "Fleet (10-15, logi)", "Combat Anomaly"),
    "World Ark Deployment Site": (5, "Fleet (10-15, logi)", "Combat Anomaly"),
    "Observatory Flashpoint": (5, "Fleet (10-15, logi)", "Combat Anomaly"),
    "Stellar Fleet Deployment Site": (5, "Cruiser fleet (10+, logi)", "Combat Anomaly"),
    "Vigilance Point": (5, "Fleet (10+, Eos/AB kiting doctrine)", "Combat Anomaly"),
    "Overmind Nursery Grove": (3, "Fast frigate/destroyer with guns + salvager", "Combat Site"),
    "Observatory Infiltration": (3, "T1 cruiser with relic analyzer (cov-ops not allowed)", "Combat Site"),
    "Deepflow rifts": (2, "Any ship with tractor beams (avoid surges)", "Combat Site"),
    "Emerging Conduit": (3, "Battleship (Praxis) solo or cruiser gang", "Combat Anomaly"),
    "Minor Conduit": (4, "Fleet (5+, logi)", "Combat Anomaly"),
    "Major Conduit": (5, "Fleet (10-15, logi)", "Combat Anomaly"),
    "EDENCOM Forward Post": (3, "Battleship (Praxis) solo or cruiser gang", "Combat Anomaly"),
    "EDENCOM Staging Area": (4, "Fleet (5+, logi)", "Combat Anomaly"),
    "EDENCOM Field Base": (5, "Fleet (10-15, logi)", "Combat Anomaly"),
    "Stellar Observation Post": (4, "Cruiser fleet (5+, logi)", "Combat Anomaly"),
}
POCHVEN_FACTION: dict[str, str] = {
    "Incipient Drone Swarm": "Rogue Drones",
    "Convocation Watchpost": "Triglavian Collective",
    "EDENCOM Scout Fleet": "EDENCOM",
    "Torpid Sleeper Hive": "Sleepers",
    "World Ark Assault Flashpoint": "Triglavian Collective",
    "World Ark Deployment Site": "Triglavian Collective",
    "Observatory Flashpoint": "EDENCOM",
    "Stellar Fleet Deployment Site": "Triglavian Collective",
    "Vigilance Point": "Triglavian Collective",
    "Overmind Nursery Grove": "Rogue Drones",
    "Observatory Infiltration": "Drifters",
    "Deepflow rifts": "Rogue Drones",
    "Emerging Conduit": "Triglavian Collective",
    "Minor Conduit": "Triglavian Collective",
    "Major Conduit": "Triglavian Collective",
    "EDENCOM Forward Post": "Triglavian Collective",
    "EDENCOM Staging Area": "Triglavian Collective",
    "EDENCOM Field Base": "Triglavian Collective",
    "Stellar Observation Post": "EDENCOM",
}
# Fallback enemy summaries for pages whose wiki text has no NPC table.
ENEMIES_FALLBACK: dict[str, str] = {
    "Minor Conduit": "5 waves of 12-15 Triglavian ships each (frigates to battleships, scrams/neuts)",
    "Major Conduit": "Large Triglavian waves incl. Leshak battleships and Zorya's named ships",
    "EDENCOM Staging Area": "Waves of Triglavian NPCs (destroyers to battleships) around the conduit",
    "EDENCOM Field Base": "Heavy Triglavian waves (cruisers to battleships) in a single ungated pocket",
    "World Ark Deployment Site": "Xordazh World Ark plus Triglavian escort fleet",
    "World Ark Assault Flashpoint": "Xordazh World Ark plus Triglavian fleet; fleet-only flashpoint",
    "Vigilance Point": "10 waves every 2 min, growing from frigates to battleships; very high DPS and heavy damps",
    "Stellar Observation Post": "EDENCOM / Triglavian cruiser-size waves (T1 cruiser gate)",
    "Advanced Drone Outgrowth Colony": "Harder variant of the Rogue Drone Outgrowth Colony (frigate/destroyer waves, "
    "boss)",
    "Observatory Flashpoint": "Waves of EDENCOM navy ships (frigates to battleships) + 1 empire dreadnought "
    "(siege/super-siege); fleet of up to 15",
    "Deepflow rifts": "Surge of ~10-15 Rogue Drone frigates/destroyers only if too many tractor beams are cycled",
    "Limited Sleeper Cache": "No ships; environmental hazards (gas clouds, proximity mines)",
    "Standard Sleeper Cache": "Sentry towers + toxic-cloud alarm hazard; no ships",
    "Superior Sleeper Cache": "Sentry towers (alpha ~4.5k), plasma chambers, shockwaves; no ships",
    "Observatory Infiltration": "8 Patient Eradicator sentries (~600 DPS) + 1 jailer if lockdown triggers; no ships",
    "Stellar Fleet Deployment Site": "Waves of Triglavian frigates to battleships (Kikimora deployables, Zorya's "
    "ships) around the Dazh Liminality Locus; cruiser-gated",
    "CHAIN Mindflood Production Facility": "Not documented; expect Blood Raider elite frigates, cruisers and "
    "battleships like other Production Facilities",
}

# Invasion-era sites that still spawn in k-space Triglavian/EDENCOM minor-victory systems and in Pochven.
MINOR_VICTORY_SITES = {
    "Minor Conduit",
    "Major Conduit",
    "EDENCOM Forward Post",
    "EDENCOM Staging Area",
    "EDENCOM Field Base",
}

# Pochven-only (True) vs Triglavian-invasion-era sites that no longer spawn (False).
POCHVEN_LIVE = {
    "Incipient Drone Swarm",
    "Convocation Watchpost",
    "EDENCOM Scout Fleet",
    "Torpid Sleeper Hive",
    "World Ark Assault Flashpoint",
    "Observatory Flashpoint",
    "Stellar Fleet Deployment Site",
    "Vigilance Point",
    "Overmind Nursery Grove",
    "Observatory Infiltration",
    "Deepflow rifts",
}

EVENT_TITLES = {
    "Wightstorm Anchorage",
    "Wightstorm Forward Base",
    "Wightstorm Muster Point",
    "Wightstorm Transit Site",
    "Union Day Combat Challenge",
    "Union Day Elite Combat Challenge",
    "Crimson Gauntlet (2020)",
    "Guri Malakim Survey Base",
    "SoCT Survey Expedition",
    "Smuggler Hideout",
    "Confiscated Smuggler Hideout",
    "Warp Matrix Convergence",
    "Rogue Drone Outgrowth Colony",
    "Advanced Drone Outgrowth Colony",
}


# --------------------------------------------------------------------------- small helpers
def _title(page: Mapping[str, Any]) -> str:
    return str(page.get("title", ""))


def _cats(page: Mapping[str, Any]) -> set[str]:
    return {str(c) for c in page.get("categories", [])}


def _ib(page: Mapping[str, Any], key: str) -> str:
    return str(page.get("infobox", {}).get(key, "") or "").strip()


def _ib_type(page: Mapping[str, Any]) -> str:
    return _ib(page, "type").lower()


def anomaly_match(title: str) -> tuple[str, str | None, int] | None:
    """Return (base, variant, tier) when ``title`` is a standard pirate/drone combat anomaly."""
    if title in DRONE_TIERS:
        return title, None, DRONE_TIERS[title]
    m = _ANOM_RE.match(title)
    if m:
        base = m.group("base")
        variant = (m.group("variant") or "").strip() or None
        return base, variant, ANOMALY_TIERS[base]
    return None


# DED pages without an infobox rating (ratings from the "Combat site" overview table).
DED_FALLBACK_RATINGS: dict[str, int] = {"Angel Military Operations Complex": 7}


def ded_rating(page: Mapping[str, Any]) -> int | None:
    m = re.search(r"(\d+)\s*/\s*10", _ib(page, "rating"))
    if m:
        return int(m.group(1))
    m = re.search(r"\((\d+)/10\)", _title(page))
    if m:
        return int(m.group(1))
    return DED_FALLBACK_RATINGS.get(_title(page))


def enemies_fallback(title: str, category: str) -> str | None:
    """Enemy summary for sites whose wiki page has no NPC table."""
    if title in ENEMIES_FALLBACK:
        return ENEMIES_FALLBACK[title]
    if title in INCURSION_TIERS:
        tier, _d, _s, note = INCURSION_TIERS[title]
        return f"Sansha's Nation incursion fleet (frigates to battleships, {tier.lower()} tier); {note}"
    return None


def wh_class(title: str) -> str | None:
    for table in (WH_ANOMALIES, WH_DATA, WH_RELIC, WH_GAS, WH_ORE):
        if title in table:
            return table[title]
    return None


def _wh_max_class(space: str) -> int:
    nums = [int(n) for n in re.findall(r"C(\d)", space)]
    return max(nums) if nums else 0


# --------------------------------------------------------------------------- classification
def classify(page: Mapping[str, Any]) -> tuple[str, str, int]:
    """Return ``(category, scan_group, is_signature)`` for a parsed page."""
    title = _title(page)
    cats = _cats(page)
    itype = _ib_type(page)
    loc = _ib(page, "location").lower()

    if title in POCHVEN_TITLES:
        sg = POCHVEN_TITLES[title][2]
        if title == "Deepflow rifts":
            return "other", sg, 1
        return "pochven", sg, 1 if sg == "Combat Site" else 0
    if title in INCURSION_TIERS or "Incursions sites" in cats:
        return "incursion", "Combat Anomaly", 0
    if title in ("Epicenter",):
        return "wormhole_combat", "Beacon", 0
    if title in ("Unknown Anomaly", "Drifter Hive(Barbican)", "Drifter Hive Anomaly", "Jove Observatory"):
        return "drifter", "Beacon", 0
    if title == "Stronghold":
        return "other", "Beacon", 0
    if title == "Rampant Drone Fabricator":
        return "wormhole_combat", "Combat Site", 1
    if title == "Hrada-Oki Bivouac":
        return "other", "Combat Site", 1
    if title in ("Limited Sleeper Cache", "Standard Sleeper Cache", "Superior Sleeper Cache"):
        return "sleeper_cache", "Data Site", 1
    if title in ("Phased Asteroid Field",) or title.startswith("Hidden ") and "Ore sites" in cats:
        return "ore", "Ore Site", 1
    if title == "Asteroid Belt Remnants":
        return "ore", "Ore Anomaly", 0
    if title == "Serpentis Capital Staging":
        return "combat_anomaly", "Combat Anomaly", 0

    # Wormhole sites (Sleeper space)
    if title in WH_ANOMALIES:
        return "wormhole_combat", "Combat Anomaly", 0
    if title in WH_DATA:
        return "wormhole_data", "Data Site", 1
    if title in WH_RELIC:
        return "wormhole_relic", "Relic Site", 1
    if title in WH_GAS:
        return "wormhole_gas", "Gas Site", 1
    if title in WH_ORE:
        return "wormhole_ore", "Ore Anomaly", 0
    if title == "Shattered Ice Field":
        return "ice", "Ice Anomaly", 0
    if title.endswith("(updated)") and "Wormhole sites" in cats:
        return "wormhole_combat", "Combat Anomaly", 0

    # Standard pirate / drone anomalies regardless of (sometimes wrong) wiki category.
    if anomaly_match(title):
        return "combat_anomaly", "Combat Anomaly", 0

    if "DED Complexes" in cats or itype == "ded" or ded_rating(page) is not None:
        return "combat_ded", "Combat Site", 1
    if itype == "combat relic" or title in COMBAT_RELIC_RUINS:
        return "relic", "Relic Site", 1
    if "Chemical Labs" in cats or itype in ("chemical", "chemical lab"):
        return "chemical_lab", "Gas Site", 1
    if "Unrated Complexes" in cats or itype == "unrated":
        return "combat_unrated", "Combat Site", 1
    if "Homefront Operations" in cats:
        return "homefront", "Combat Anomaly", 0
    if "Combat Anomalies" in cats or itype in ("anomaly", "anaomaly"):
        if "pochven" in loc:
            return "pochven", "Combat Anomaly", 0
        return "combat_anomaly", "Combat Anomaly", 0
    if "Ice belts" in cats:
        return "ice", "Ice Anomaly", 0
    if cats & {"Ore sites", "Rare ore sites", "Removed ore sites", "Sovereignty Hub ore deposits"}:
        return "ore", "Ore Anomaly", 0
    if "Gas sites" in cats or itype in ("cytoserocin", "mykoserocin", "cosmos"):
        return "gas", "Gas Site", 1
    if "Relic sites" in cats or itype == "relic":
        return "relic", "Relic Site", 1
    if "Data sites" in cats or itype == "data site":
        return "data", "Data Site", 1
    return "other", "Combat Site", 1


# --------------------------------------------------------------------------- space
_SEC_WORDS = (
    (re.compile(r"\bhigh", re.I), "High"),
    (re.compile(r"\blow", re.I), "Low"),
    (re.compile(r"\bnull", re.I), "Null"),
)
NULL_REGIONS = {
    "catch",
    "delve",
    "vale of the silent",
    "vale",
    "tenal",
    "fountain",
    "cloud ring",
    "wicked creek",
    "feythabolis",
    "curse",
    "insmother",
    "omist",
    "tenerifis",
    "detorid",
    "great wildlands",
    "immensea",
    "venal",
    "pure blind",
    "syndicate",
    "outer passage",
    "the spire",
    "etherium reach",
    "perrigen falls",
    "malpais",
    "cobalt edge",
    "providence",
    "stain",
    "esoteria",
    "paragon soul",
    "period basis",
    "querious",
    "deklein",
    "branch",
    "tribute",
    "geminate",
    "scalding pass",
    "outer ring",
    "cache",
    "impass",
    "oasa",
    "kalevala expanse",
    "the kalevala expanse",
}
LOW_REGIONS_HINT = {
    "aridia",
    "solitude",
    "placid",
    "molden heath",
    "heimatar",
    "derelik",
    "black rise",
    "lonetrek",
    "the forge",
    "genesis",
    "essence",
    "verge vendor",
    "sinq laison",
    "everyshore",
    "domain",
    "kador",
    "kor-azor",
    "khanid",
    "tash-murkon",
    "devoid",
    "the bleak lands",
    "metropolis",
    "the citadel",
}


def normalise_space(raw: str) -> str:
    """Normalise a free-text location into "High", "Low, Null", "C5", "Pochven" ..."""
    text = (raw or "").strip()
    if not text:
        return ""
    low = text.lower()
    if "pochven" in low:
        return "Pochven"
    m = re.search(r"\bC(\d)\b", text)
    if m and ("wormhole" in low or re.fullmatch(r"c\d", low)):
        return f"C{m.group(1)}"
    if "c1-6" in low or "c1-c6" in low or "all classes of wormhole" in low:
        return "C1-C6"
    if "wormhole" in low or "w-space" in low:
        return "Wormhole"
    parts = [label for pat, label in _SEC_WORDS if pat.search(text)]
    if parts:
        return ", ".join(parts)
    return text


def space_of(page: Mapping[str, Any], category: str) -> str:
    title = _title(page)
    cats = _cats(page)
    raw = _ib(page, "location")

    if category in ("wormhole_combat", "wormhole_data", "wormhole_relic", "wormhole_gas", "wormhole_ore"):
        cls = wh_class(title)
        if cls:
            return cls
        if title == "Epicenter":
            return "Shattered, Thera"
        if title == "Rampant Drone Fabricator":
            return "C1-C6"
        base = title.replace("(updated)", "").strip()
        return wh_class(base) or normalise_space(raw) or "Wormhole"
    if category == "ice" and title == "Shattered Ice Field":
        return "Shattered"
    if category == "pochven" or title in POCHVEN_TITLES:
        if title == "Observatory Infiltration":
            return "Low, Pochven"
        if title == "Deepflow rifts":
            return "High, Low, Null, Wormhole, Pochven"
        if title in MINOR_VICTORY_SITES:
            return "Triglavian/EDENCOM minor-victory systems; Pochven"
        if title == "Stellar Observation Post":
            return "EDENCOM minor-victory systems"
        if title == "Emerging Conduit":
            return "High (2019-2020 version)"
        return "Pochven"
    if category == "incursion":
        if title == "Uroborus":
            return "Incursion constellation (Low)"
        if title == "The Kundalini Manifest":
            return "Incursion constellation (High, Null)"
        return "Incursion constellation (High, Low, Null)"
    if category == "drifter":
        if title == "Jove Observatory":
            return "High, Low, Null (Jove Observatory systems)"
        if title == "Unknown Anomaly":
            return "Wormhole"
        if title == "Drifter Hive(Barbican)":
            return "Drifter wormhole (Barbican, J110145)"
        if title == "Drifter Hive Anomaly":
            return "Drifter wormhole (Conflux, J200727)"
        return "Drifter wormhole"
    if title == "Stronghold":
        return "Low"
    if title == "Hrada-Oki Bivouac":
        return "Wormhole"
    if category == "homefront":
        return "High"

    am = anomaly_match(title)
    if am and category == "combat_anomaly":
        base, variant, tier = am
        if variant and tier in ANOMALY_VARIANT_SPACE:
            return ANOMALY_VARIANT_SPACE[tier]
        return ANOMALY_SPACE[tier]

    if category == "combat_unrated":
        for pat, space, _d, _s in UNRATED_RULES:
            if pat.search(title):
                return space
    if category == "combat_ded":
        norm = normalise_space(raw)
        if norm:
            return norm
        r = ded_rating(page)
        if r is not None:
            return {
                1: "High, Low",
                2: "High, Low",
                3: "High, Low",
                4: "High, Low",
                5: "High, Low",
                6: "Low, Null",
                7: "Null",
                8: "Null",
                10: "Null",
            }.get(r, "Unknown")
    if category == "relic" and title in COMBAT_RELIC_RUINS:
        norm = normalise_space(raw)
        return (
            norm
            if norm in ("Null", "Low, Null")
            else f"Null ({raw})"
            if raw and raw.lower() not in ("null",)
            else "Null"
        )
    if category == "ore":
        if "Sovereignty Hub ore deposits" in cats or "Cluster" in title:
            return "Null (sov hub upgrade)"
        if "Rare ore sites" in cats:
            if title.startswith("Empire Border"):
                return "High, Low (border systems)"
            if title.startswith("W-Space"):
                return "Wormhole (A0 blue star)"
            return "Null"
        if title in ("Interstitial Ore Deposit", "Veiled Asteroid Field"):
            return "Null (mining escalation)"
        if title == "Asteroid Belt Remnants":
            return "High (starter systems, 1.0-0.7)"
        if title == "Phased Asteroid Field":
            return "Low, Null"
        if title.startswith("Hidden "):
            return "Low"
        if any(w in title for w in ("Omber", "Kernite")):
            return "High (0.5-0.8)" if "Kernite" in title or "Omber" in title else "High"
        if any(w in title for w in ("Arkonor", "Bistot", "Mercoxit")):
            return "Null"
        return "Low"
    if category == "ice":
        if title.startswith(("Enriched", "Pristine", "Thick", "Smooth")):
            return "Null"
        return "High, Low"
    if category == "gas":
        itype = _ib_type(page)
        if itype == "mykoserocin":
            return "High, Low, Null"
        if raw:
            region = re.sub(r"\s*\(.*?\)", "", raw)
            region = region.replace("Low Security Systems in", "").replace("Region", "").strip(" .")
            region = re.sub(r"\s+", " ", region)
            lowr = region.lower()
            if "low" in raw.lower() and "sec" in raw.lower():
                return f"Low ({region.replace('low security systems', '').strip() or raw})"
            if any(r in lowr for r in NULL_REGIONS):
                return f"Null ({region})"
            if itype == "mykoserocin":
                return f"High, Low, Null ({region})" if region else "High, Low, Null"
            return f"Low/Null ({region})" if region else "Low, Null"
        return "High, Low, Null" if itype == "mykoserocin" else "Low, Null"
    if category == "chemical_lab":
        norm = normalise_space(raw)
        if norm in ("High", "Low", "Null", "Low, Null", "High, Low"):
            return norm
        if raw:
            region = re.sub(r"\{\{.*?\}\}", "", raw).strip()
            region = re.sub(r"\s*\(.*?\)", "", region)
            return f"Null ({region})" if region.lower() in NULL_REGIONS else f"Low ({region})"
        return "Low, Null"
    if category == "data":
        if title.startswith("Abandoned Research Complex"):
            return "Null (Drone regions)"
        if title == "AEGIS Capital Ship Security Facility":
            return "Low, Null"
        if title == "SCC Secure Key Storage":
            return "Low"
        if title == "Interrupted Expedition":
            return "High, Low, Null (escalation)"
        if title == "Contested Covert Research Facilities":
            return "High, Low, Null"
    if category == "relic" and title == "Emergent Ruins":
        return "High, Low, Null (escalation)"
    if category == "sleeper_cache":
        return "High, Low, Null"
    if title in EVENT_TITLES:
        norm = normalise_space(raw)
        return norm or "High, Low, Null"
    norm = normalise_space(raw)
    return norm or "Unknown"


# --------------------------------------------------------------------------- faction
FACTION_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"angel|gist|domination|cartel", re.I), "Angel Cartel"),
    (re.compile(r"blood|corp(ii|ior|um|atis|us)|dark blood|crimson|covenant", re.I), "Blood Raiders"),
    (re.compile(r"gurista|pith|dread gurista", re.I), "Guristas"),
    (re.compile(r"sansha|centi|true sansha|true power|true creations|nation", re.I), "Sansha's Nation"),
    (re.compile(r"serpentis|corel|shadow serpentis", re.I), "Serpentis"),
    (re.compile(r"rogue drone|drone|alvus|strain", re.I), "Rogue Drones"),
    (re.compile(r"sleeper|hypnosian", re.I), "Sleepers"),
    (re.compile(r"drifter|tyrannos|lancer", re.I), "Drifters"),
    (re.compile(r"trig|raznaborg|zorya", re.I), "Triglavian Collective"),
    (re.compile(r"edencom", re.I), "EDENCOM"),
    (re.compile(r"mordu", re.I), "Mordu's Legion"),
    (re.compile(r"concord|scc|ded|saro", re.I), "CONCORD/SCC"),
    (re.compile(r"amarr", re.I), "Amarr Navy"),
    (re.compile(r"caldari", re.I), "Caldari Navy"),
    (re.compile(r"gallente|federation", re.I), "Gallente Navy"),
    (re.compile(r"minmatar|republic", re.I), "Minmatar Navy"),
    (re.compile(r"sisters|soe|sanctuary", re.I), "Sisters of EVE"),
    (re.compile(r"upwell", re.I), "Upwell"),
]


CHEM_LAB_PREFIXES: list[tuple[str, str]] = [
    ("CHAIN", "Blood Raiders"),
    ("Core Runner", "Serpentis"),
    ("Elohim", "Angel Cartel"),
    ("H-PA Crew", "Guristas"),
    ("PDW-09FX", "Sansha's Nation"),
]


def faction_of(page: Mapping[str, Any]) -> str | None:
    title = _title(page)
    if title in POCHVEN_FACTION:
        return POCHVEN_FACTION[title]
    for prefix, faction in CHEM_LAB_PREFIXES:
        if title.startswith(prefix):
            return faction
    for source in (_ib(page, "faction"), _ib(page, "faction1")):
        if source:
            for pat, name in FACTION_ALIASES:
                if pat.search(source):
                    return name
    # Wormhole Sleeper sites
    if wh_class(title) or title in ("Epicenter",) or title.endswith("(updated)"):
        return "Sleepers"
    if title in ("Unknown Anomaly", "Jove Observatory") or title.startswith("Drifter Hive"):
        return "Drifters"
    if title in INCURSION_TIERS:
        return "Sansha's Nation"
    if (
        title == "Rampant Drone Fabricator"
        or title.startswith("Abandoned Research Complex")
        or title == "Overmind Nursery Grove"
    ):
        return "Rogue Drones"
    if title == "Stronghold":
        return "Guristas / Blood Raiders"
    if title == "Besieged Covert Research Facility":
        return "Mordu's Legion"
    if title in ("SCC Secure Key Storage",):
        return "CONCORD/SCC"
    if title == "Observatory Infiltration":
        return "Drifters"
    if title == "Deepflow rifts":
        return "Rogue Drones"
    for pat, name in FACTION_ALIASES[:9]:
        if pat.search(title):
            return name
    # Fall back to the NPC names in the tables.
    names = " ".join(str(r.get("name", "")) for r in page.get("npc_rows", []) if r.get("hostile", True))
    for pat, name in FACTION_ALIASES:
        if pat.search(names):
            return name
    return None


# --------------------------------------------------------------------------- enemies
_VARIANT_RE = re.compile(
    r"variant|\bor\b|^(amarr|caldari|gallente|minmatar)\b|highsec|lowsec|nullsec|4-bunker|turret ring", re.I
)
_EWAR_TOKENS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"scram", re.I), "scram"),
    (re.compile(r"\bweb|stasis", re.I), "web"),
    (re.compile(r"\bpoint\b|disrupt|^yes$", re.I), "point"),
    (re.compile(r"neut", re.I), "neut"),
    (re.compile(r"damp", re.I), "damp"),
    (re.compile(r"\btd\b|tracking disrupt|weapon disrupt", re.I), "td"),
    (re.compile(r"\btp\b|paint", re.I), "tp"),
    (re.compile(r"ecm|jam", re.I), "ecm"),
    (re.compile(r"\brr\b|remote rep", re.I), "rr"),
]
_EWAR_ORDER = ("web", "scram", "point", "neut", "damp", "td", "tp", "ecm", "rr")


def _fmt_range(lo: int | None, hi: int | None) -> str:
    if lo is None and hi is None:
        return "some"
    if lo is None:
        return f"up to {hi}"
    if hi is None:
        return f"{lo}+"
    return str(lo) if lo == hi else f"{lo}-{hi}"


def _plural(cls: str, count_hi: int | None, count_lo: int | None) -> str:
    one = count_hi == 1 and (count_lo in (0, 1, None))
    if one:
        return cls
    return _PLURAL.get(cls, cls + "s")


_PAREN_SECTION_RE = re.compile(r"^(?P<prefix>[^(]+?)\s*\((?P<alt>[^)]+)\)\s*$")


def _collapse_alternate_pockets(rows: list[Mapping[str, Any]]) -> tuple[list[Mapping[str, Any]], bool]:
    """Keep only the heaviest of alternative pockets such as "3rd Pocket (Supply Depot)" / "3rd Pocket (Watchpost)"."""
    by_prefix: dict[str, dict[str, list[Mapping[str, Any]]]] = {}
    for r in rows:
        m = _PAREN_SECTION_RE.match(str(r.get("section") or ""))
        if m:
            by_prefix.setdefault(m.group("prefix").strip().lower(), {}).setdefault(m.group("alt"), []).append(r)
    drop: set[int] = set()
    collapsed = False
    for alts in by_prefix.values():
        if len(alts) < 2:
            continue
        collapsed = True
        best = max(alts, key=lambda a: _weight(_sum_rows(alts[a])))
        for alt, group in alts.items():
            if alt != best:
                drop.update(id(r) for r in group)
    return [r for r in rows if id(r) not in drop], collapsed


def _group_variants(rows: list[Mapping[str, Any]]) -> list[list[Mapping[str, Any]]]:
    """Split rows into alternative variants (by section/wave hints); returns one group if none."""
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for r in rows:
        key = str(r.get("section") or "")
        wave = str(r.get("wave") or "")
        tag = key if _VARIANT_RE.search(key) else (wave if _VARIANT_RE.search(wave) and not key else "")
        groups.setdefault(tag, []).append(r)
    if len(groups) <= 1:
        return [rows]
    common = groups.pop("", [])
    return [common + g for g in groups.values()]


def _sum_rows(rows: Iterable[Mapping[str, Any]]) -> dict[str, tuple[int | None, int | None, bool]]:
    totals: dict[str, list[Any]] = {}
    for r in rows:
        cls = str(r.get("ship_class"))
        if cls not in CLASS_ORDER:
            continue
        lo, hi = r.get("count_min"), r.get("count_max")
        if lo == 0 and hi == 0:  # "0-?" style counts: present but unknown
            lo = hi = None
        t = totals.setdefault(cls, [0, 0, False, False])
        if lo is None and hi is None:
            t[3] = True
        else:
            t[0] += int(lo if lo is not None else hi)
            t[1] += int(hi if hi is not None else lo)
        if r.get("tier"):
            t[2] = True
    out: dict[str, tuple[int | None, int | None, bool]] = {}
    for cls, (lo, hi, tier, unknown) in totals.items():
        if unknown and lo == 0 and hi == 0:
            out[cls] = (None, None, tier)
        elif unknown:
            out[cls] = (lo, None, tier)
        else:
            out[cls] = (lo, hi, tier)
    return out


def _weight(totals: Mapping[str, tuple[int | None, int | None, bool]]) -> int:
    weights = {
        "frigate": 1,
        "destroyer": 2,
        "cruiser": 4,
        "battlecruiser": 6,
        "battleship": 10,
        "dreadnought": 40,
        "carrier": 40,
        "supercarrier": 80,
        "titan": 120,
        "fighter": 2,
        "drone": 1,
        "sentry": 2,
    }
    return sum(weights.get(c, 1) * ((hi if hi is not None else lo) or 1) for c, (lo, hi, _t) in totals.items())


def aggregate_enemies(
    npc_rows: Iterable[Mapping[str, Any]], faction: str | None = None, combat: bool = True
) -> tuple[str, str | None, list[dict[str, Any]]]:
    """Summarise hostile NPC rows: ``(summary, ewar, enemy_rows)``.

    ``enemy_rows`` are the hostile rows normalised for the ``site_enemies`` table.
    """
    rows = [r for r in npc_rows if r.get("hostile", True) and r.get("ship_class") in CLASS_ORDER]
    enemy_rows = [
        {
            "wave": (f"{r.get('section')} / {r.get('wave')}" if r.get("section") else r.get("wave")),
            "ship_class": r.get("ship_class"),
            "count_min": r.get("count_min"),
            "count_max": r.get("count_max"),
            "name": r.get("name"),
            "tier": r.get("tier"),
            "ewar": ", ".join(r.get("ewar") or []) or None,
        }
        for r in rows
    ]
    ewar_set: set[str] = set()
    for r in rows:
        for e in r.get("ewar") or []:
            for pat, tok in _EWAR_TOKENS:
                if pat.search(str(e)):
                    ewar_set.add(tok)
    ewar = ", ".join(t for t in _EWAR_ORDER if t in ewar_set) or None

    if not rows:
        return ("Unknown" if combat else "None"), ewar, enemy_rows

    rows, collapsed = _collapse_alternate_pockets(rows)
    groups = _group_variants(rows)
    per_variant = len(groups) > 1 or collapsed
    totals = max((_sum_rows(g) for g in groups), key=_weight)
    prefix = "Sleeper " if faction == "Sleepers" else ""
    parts: list[str] = []
    any_tier = False
    for cls in CLASS_ORDER:
        if cls not in totals:
            continue
        lo, hi, tier = totals[cls]
        any_tier = any_tier or tier
        label = _plural(cls, hi, lo)
        if cls in ("sentry", "drone", "fighter"):
            parts.append(f"{_fmt_range(lo, hi)} {label}")
        else:
            parts.append(f"{_fmt_range(lo, hi)} {prefix}{label}")
    summary = ", ".join(parts)
    if any_tier:
        summary += " (incl. commander/overseer)"
    if per_variant:
        summary += " (per variant)"
    return summary, ewar, enemy_rows


def has_class(npc_rows: Iterable[Mapping[str, Any]], *classes: str) -> bool:
    return any(r.get("hostile", True) and r.get("ship_class") in classes for r in npc_rows)


# --------------------------------------------------------------------------- rating
def rating_of(page: Mapping[str, Any], category: str) -> str | None:
    title = _title(page)
    raw = _ib(page, "rating")
    r = ded_rating(page)
    if category == "combat_ded":
        return f"{r}/10" if r is not None else (raw or None)
    if category in ("wormhole_combat", "wormhole_data", "wormhole_relic", "wormhole_gas", "wormhole_ore"):
        return wh_class(title.replace("(updated)", "").strip()) or (raw or None)
    am = anomaly_match(title)
    if am:
        base, variant, tier = am
        level = {None: 1, "Hidden": 2, "Forsaken": 3, "Forlorn": 4}[variant]
        return f"Tier {tier}" + (f" Level {level}" if variant else "")
    if category == "incursion" and title in INCURSION_TIERS:
        return INCURSION_TIERS[title][0]
    if category in ("combat_unrated", "chemical_lab"):
        return "Unrated"
    if raw and raw.lower() not in ("none", "n/a", "na", ""):
        return raw
    return None


# --------------------------------------------------------------------------- danger
def danger_of(page: Mapping[str, Any], category: str, space: str) -> int:
    """Danger 0-5; battleship-class hostiles always lift a site to at least Medium."""
    d = _danger_base(page, category, space)
    rows = page.get("npc_rows", [])
    if (
        category != "wormhole_connection"
        and d < 3
        and has_class(rows, "battleship", "dreadnought", "carrier", "supercarrier", "titan")
    ):
        d = 3
    return d


def _danger_base(page: Mapping[str, Any], category: str, space: str) -> int:
    title = _title(page)
    rows = page.get("npc_rows", [])
    hostile = [r for r in rows if r.get("hostile", True)]
    has_bs = has_class(rows, "battleship", "dreadnought", "carrier", "supercarrier", "titan")

    if title in POCHVEN_TITLES:
        return POCHVEN_TITLES[title][0]
    if title in INCURSION_TIERS:
        return INCURSION_TIERS[title][1]
    if category == "combat_ded":
        r = ded_rating(page)
        d = 3
        if r is not None:
            d = 2 if r <= 3 else 3 if r <= 6 else 4 if r <= 8 else 5
        return d
    am = anomaly_match(title)
    if am and category == "combat_anomaly":
        _b, variant, tier = am
        d = 2 if tier <= 3 else 3 if tier <= 6 else 4 if tier <= 9 else 5
        if variant in ("Forsaken", "Forlorn") and tier == 6:
            d = 4  # elite Rally Point variants field 15-25 battleships
        if has_bs and d < 3:
            d = 3
        return d
    if category == "combat_unrated":
        for pat, _space, d, _ship in UNRATED_RULES:
            if pat.search(title):
                return 3 if (has_bs and d < 3) else d
        return 3 if not has_bs else 4
    if category == "relic" and title in COMBAT_RELIC_RUINS:
        return 4
    if category == "chemical_lab":
        return 4 if has_bs else 3
    if category == "sleeper_cache":
        return {"Limited Sleeper Cache": 2, "Standard Sleeper Cache": 3, "Superior Sleeper Cache": 4}.get(title, 3)
    if category == "data":
        if title == "SCC Secure Key Storage":
            return 5
        if title == "AEGIS Capital Ship Security Facility":
            return 3
        if title.startswith("Abandoned Research Complex"):
            return 2
        if title == "Contested Covert Research Facilities":
            return 2
        return 2 if hostile else 1
    if category == "relic":
        return 2 if hostile else 1
    if category == "gas":
        if has_bs:
            return 4
        if has_class(rows, "cruiser", "battlecruiser"):
            return 3
        guarded = _ib(page, "is guarded").lower().startswith("y")
        damage = _ib(page, "cloud damage").lower() not in ("", "none", "?")
        return 2 if (guarded or damage or hostile) else 1
    if category in ("wormhole_combat", "wormhole_data", "wormhole_relic"):
        if title == "Epicenter":
            return 3
        if title == "Rampant Drone Fabricator":
            return 4
        c = _wh_max_class(space)
        return 3 if c <= 2 else 4 if c <= 4 else 5
    if category in ("wormhole_gas", "wormhole_ore"):
        return 4 if space.startswith("C5") else 3  # Core sites only spawn in C5/C6
    if category in ("ore", "ice"):
        return 1
    if category == "drifter":
        return 5
    if category == "homefront":
        return 4
    if title == "Stronghold":
        return 5
    if title == "Besieged Covert Research Facility":
        return 4
    if title == "Serpentis Capital Staging":
        return 5
    if title == "Hrada-Oki Bivouac":
        return 1
    if category == "combat_anomaly":
        # Event / misc anomalies: judge from composition.
        if has_bs:
            return 4
        if has_class(rows, "battlecruiser", "cruiser"):
            return 3
        return 2 if hostile else 3
    return 3 if hostile else 1


# --------------------------------------------------------------------------- min ship
_LIMIT_WORDS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"frigate", re.I), 0),
    (re.compile(r"destroyer", re.I), 1),
    (re.compile(r"cruiser(?!s? and below)", re.I), 2),  # "T1 Cruiser and below" handled below
    (re.compile(r"battlecruiser|\bBC\b|T3C", re.I), 3),
    (re.compile(r"battleship", re.I), 4),
]


def ship_limit_index(limit: str | None) -> int | None:
    """Largest size-ladder index an acceleration gate allows, or None if unrestricted/unknown."""
    if not limit:
        return None
    low = limit.lower()
    if any(
        w in low for w in ("unrestricted", "unknown", "no limit", "ungated", "unverified", "tbc", "titan", "capital")
    ):
        return None
    idx: int | None = None
    if "battleship" in low:
        idx = 4
    elif "battlecruiser" in low or "t3c" in low or "t3 cruiser" in low or "strategic" in low:
        idx = 3
    elif "cruiser" in low:
        idx = 2
    elif "destroyer" in low:
        idx = 1
    elif "frigate" in low:
        idx = 0
    return idx


def _phrase_index(phrase: str) -> int:
    low = phrase.lower()
    if low.startswith("t1 frigate"):
        return 0
    if low.startswith("destroyer"):
        return 1
    if low.startswith("t1 cruiser"):
        return 2
    if low.startswith("battlecruiser"):
        return 3
    return 4


def cap_by_limit(phrase: str, limit: str | None) -> str:
    cap = ship_limit_index(limit)
    if cap is None:
        return phrase
    if _phrase_index(phrase) > cap:
        return SHIP_PHRASES[SIZE_LADDER[cap]]
    return phrase


DED_SHIPS = {
    1: "T1 frigate",
    2: "Destroyer",
    3: "T1 cruiser (Vexor/Caracal/Omen/Rupture)",
    4: "Battlecruiser (Drake/Gnosis/Myrmidon)",
    5: "Battlecruiser / Battleship",
    6: "Battleship / T3C",
    7: "Battleship (Dominix/Rattlesnake/Praxis)",
    8: "Marauder / Rattlesnake",
    9: "Marauder; 2+ pilots recommended",
    10: "Marauder; 2+ pilots recommended",
}
TIER_SHIPS = {
    1: "T1 frigate",
    2: "Destroyer",
    3: "Destroyer",
    4: "T1 cruiser (Vexor/Caracal/Omen/Rupture)",
    5: "T1 cruiser (Vexor/Caracal/Omen/Rupture)",
    6: "Battlecruiser (Drake/Gnosis/Myrmidon)",
    7: "Battlecruiser / Battleship",
    8: "Battleship (Dominix/Rattlesnake/Praxis)",
    9: "Battleship (Dominix/Rattlesnake/Praxis)",
    10: "Marauder / Rattlesnake",
}
_STEP_UP = {
    "T1 frigate": "Destroyer",
    "Destroyer": "T1 cruiser (Vexor/Caracal/Omen/Rupture)",
    "T1 cruiser (Vexor/Caracal/Omen/Rupture)": "Battlecruiser (Drake/Gnosis/Myrmidon)",
    "Battlecruiser (Drake/Gnosis/Myrmidon)": "Battlecruiser / Battleship",
    "Battlecruiser / Battleship": "Battleship (Dominix/Rattlesnake/Praxis)",
    "Battleship (Dominix/Rattlesnake/Praxis)": "Marauder / Rattlesnake",
    "Marauder / Rattlesnake": "Marauder; 2+ pilots recommended",
}
WH_SHIPS = {
    1: "Cruiser / BC (Gnosis/Drake)",
    2: "Battlecruiser / T3C",
    3: "T3C / Rattlesnake / Marauder",
    4: "Marauder / 2+ T3Cs",
    5: "Marauder gang (dreadnought escalation)",
    6: "Marauder/capital fleet",
}
EXPLO_FRIGATE = "T1 explo frigate (Heron/Probe/Imicus/Magnate)"


def min_ship_of(page: Mapping[str, Any], category: str, space: str, danger: int) -> str:
    title = _title(page)
    rows = page.get("npc_rows", [])
    limit = _ib(page, "ship limit") or None
    hostile = [r for r in rows if r.get("hostile", True)]

    if title in POCHVEN_TITLES:
        return POCHVEN_TITLES[title][1]
    if title in INCURSION_TIERS:
        return INCURSION_TIERS[title][2]
    if category == "combat_ded":
        r = ded_rating(page)
        return cap_by_limit(DED_SHIPS.get(r or 5, "Battleship / T3C"), limit)
    am = anomaly_match(title)
    if am and category == "combat_anomaly":
        _b, variant, tier = am
        phrase = TIER_SHIPS[tier]
        if variant:  # Hidden / Forsaken / Forlorn variants spawn more and tougher ships
            phrase = _STEP_UP.get(phrase, phrase)
        return phrase
    if category == "combat_unrated":
        for pat, _space, _d, ship in UNRATED_RULES:
            if pat.search(title):
                return cap_by_limit(ship, limit)
        return cap_by_limit("Battlecruiser / Battleship", limit)
    if category == "relic" and title in COMBAT_RELIC_RUINS:
        return cap_by_limit("Battleship / T3C with relic analyzer", limit)
    if category == "chemical_lab":
        return cap_by_limit(
            "Battleship / T3C with data analyzer" if danger >= 4 else "Battlecruiser with data analyzer", limit
        )
    if category == "sleeper_cache":
        return {
            "Limited Sleeper Cache": "Tanked explo frigate / Astero (mobile depot, refits)",
            "Standard Sleeper Cache": "Astero / Stratios (mobile depot, refits)",
            "Superior Sleeper Cache": "Stratios / T3C (mobile depot, refits)",
        }.get(title, "Astero / Stratios")
    if category == "data":
        if title == "SCC Secure Key Storage":
            return "Marauder + 2 hacking ships"
        if title == "AEGIS Capital Ship Security Facility":
            return "Cov-ops / T1 explo frigate (T2 analyzer)"
        if title.startswith("Abandoned Research Complex"):
            return "T1 explo frigate with light drones/missiles"
        if title == "Contested Covert Research Facilities":
            return "Tanked explo frigate (2-3 tank modules)"
        return EXPLO_FRIGATE if not hostile else "Tanked explo frigate / Astero"
    if category == "relic":
        return EXPLO_FRIGATE if not hostile else "Tanked explo frigate / Astero"
    if category == "gas":
        if hostile:
            if has_class(rows, "battleship"):
                return "Battleship to clear, then Venture"
            if has_class(rows, "cruiser", "battlecruiser"):
                return "Cruiser to clear, then Venture"
            return "Destroyer to clear, then Venture"
        if _ib(page, "is guarded").lower().startswith("y"):
            return "Destroyer to clear, then Venture"
        if _ib(page, "cloud damage").lower() not in ("", "none", "?"):
            return "Venture (clouds deal damage; tank it)"
        return "Venture"
    if category == "wormhole_gas":
        return "Venture (warp out when Sleepers land)"
    if category == "wormhole_ore":
        return "Procurer / Venture (Sleepers spawn)"
    if category in ("wormhole_combat", "wormhole_data", "wormhole_relic"):
        if title == "Epicenter":
            return "Cruiser / BC (Gnosis/Drake)"
        if title == "Rampant Drone Fabricator":
            return "Cruiser gang (3-5); solo possible for early waves"
        c = _wh_max_class(space) or 3
        return WH_SHIPS[min(max(c, 1), 6)]
    if category == "ore":
        if title == "Phased Asteroid Field":
            return "Industrial command ship (Porpoise/Orca/Rorqual) + Mobile Phase Anchor"
        if title == "Asteroid Belt Remnants":
            return "Venture / corvette"
        return "Venture"
    if category == "ice":
        return "Endurance / mining barge" if title != "Shattered Ice Field" else "Endurance / Procurer (Sleepers spawn)"
    if category == "drifter":
        if title == "Jove Observatory":
            return "Any ship (stay >50 km, leave if Drifters arrive)"
        return "Fleet (20-30, logi, tracking disruptors)"
    if category == "homefront":
        return (
            "Fleet of 3 T1 cruisers + logi"
            if title in ("Salvage Research", "Traffic Stop", "Stabilize Rift")
            else "Fleet of 5 T1 cruisers + logi"
        )
    if title == "Stronghold":
        return "Fleet (10+, logi)"
    if title == "Besieged Covert Research Facility":
        return "Gila / stealth bomber (kinetic)"
    if title == "Serpentis Capital Staging":
        return "Battleship gang / dreadnought"
    if title == "Hrada-Oki Bivouac":
        return "Any ship"
    if category == "combat_anomaly":
        phrase = {
            2: "Destroyer",
            3: "T1 cruiser (Vexor/Caracal/Omen/Rupture)",
            4: "Battleship / T3C",
            5: "Fleet (5+, logi)",
        }.get(danger, "Battlecruiser (Drake/Gnosis/Myrmidon)")
        return cap_by_limit(phrase, limit)
    return {
        1: "Any ship",
        2: "Destroyer",
        3: "T1 cruiser (Vexor/Caracal/Omen/Rupture)",
        4: "Battleship / T3C",
        5: "Fleet (5+, logi)",
    }.get(danger, "Unknown")


# --------------------------------------------------------------------------- status
def status_of(page: Mapping[str, Any], category: str) -> str:
    title = _title(page)
    flags = page.get("flags", {})
    cats = _cats(page)
    if title in MINOR_VICTORY_SITES:
        return "active"
    if flags.get("past_content"):
        return "removed"
    if title in POCHVEN_TITLES and title not in POCHVEN_LIVE:
        return "removed"
    if "Removed ore sites" in cats:
        if "Omber" in title:  # Omber / Kernite+Omber deposits re-added in Catalyst (Nov 2025)
            return "active"
        return "removed"
    if title in EVENT_TITLES or "Game events" in cats:
        return "event"
    return "active"


def ship_limit_of(page: Mapping[str, Any]) -> str | None:
    limit = _ib(page, "ship limit")
    if not limit or limit.lower() in ("", "unknown", "unverified"):
        return None
    return limit[:80]


def source_url(title: str) -> str:
    return "https://wiki.eveuniversity.org/" + title.replace(" ", "_")


# --------------------------------------------------------------------------- controlled vocabularies
CANONICAL_FACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"soct|society of conscious", re.I), "Society of Conscious Thought"),
    (re.compile(r"saro", re.I), "CONCORD/SARO"),
    (re.compile(r"concord|\bded\b", re.I), "CONCORD/SCC"),
    (re.compile(r"guri malakim", re.I), "Guri Malakim"),
    (re.compile(r"order of tetrimon|tetrimon", re.I), "Order of Tetrimon"),
    (re.compile(r"purity of the throne", re.I), "Purity of the Throne"),
    (re.compile(r"underworld smuggler", re.I), "Underworld Smugglers"),
    (re.compile(r"shining flame", re.I), "Shining Flame"),
    (re.compile(r"ashes of turnur", re.I), "Ashes of Turnur"),
    (re.compile(r"disciples of purity", re.I), "Disciples of Purity"),
    (re.compile(r"gallentia primacy", re.I), "Gallentia Primacy"),
    (re.compile(r"united champions", re.I), "United Champions of Freedom"),
    (re.compile(r"nemesis", re.I), "Nemesis"),
    (re.compile(r"aegis", re.I), "AEGIS"),
    (re.compile(r"mordu", re.I), "Mordu's Legion"),
    (re.compile(r"\bore\b", re.I), "ORE"),
    (re.compile(r"upwell", re.I), "Upwell"),
    (re.compile(r"deathless", re.I), "Deathless Circle"),
    (re.compile(r"drifter|tyrannos|lancer", re.I), "Drifters"),
    (re.compile(r"sleeper|hypnosian", re.I), "Sleepers"),
    (re.compile(r"trig|raznaborg|zorya", re.I), "Triglavian Collective"),
    (re.compile(r"edencom", re.I), "EDENCOM"),
    (re.compile(r"rogue drone|\bdrone", re.I), "Rogue Drones"),
    (re.compile(r"angel|gist|cartel", re.I), "Angel Cartel"),
    (re.compile(r"blood|corp(ii|ior|um|atis|us)|crimson|covenant", re.I), "Blood Raiders"),
    (re.compile(r"gurista|pith", re.I), "Guristas"),
    (re.compile(r"sansha|centi", re.I), "Sansha's Nation"),
    (re.compile(r"serpentis|corel", re.I), "Serpentis"),
    (re.compile(r"amarr", re.I), "Amarr Navy"),
    (re.compile(r"caldari", re.I), "Caldari Navy"),
    (re.compile(r"gallente|federation", re.I), "Gallente Navy"),
    (re.compile(r"minmatar|republic", re.I), "Minmatar Navy"),
    (re.compile(r"empire|navy|mercenar", re.I), "Empire navies"),
]


def canonical_faction(raw: object) -> str | None:
    """Short canonical faction label (<= 40 chars, never ends on an open parenthesis) or None."""
    text = str(raw or "").strip()
    if not text or text.lower().startswith(("unknown", "none", "n/a", "varies")):
        return None
    head = re.split(r"\s*\(|,|;| and | or |/", text, maxsplit=1)[0].strip()
    if re.search(r"slaver", head, re.I):
        return "Amarr slavers"
    label = head
    for pat, name in CANONICAL_FACTIONS:
        if pat.search(head):
            label = name
            break
    label = label.strip(" ,(/")
    if len(label) > 40:
        label = label[:40].rsplit(" ", 1)[0].rstrip(" ,(/")
    return label or None


SHIP_VOCAB_DEFAULT: dict[int, str] = {
    0: "Unknown",
    1: "Any ship",
    2: "Destroyer",
    3: "T1 cruiser (Vexor/Caracal/Omen/Rupture)",
    4: "Battleship / T3C",
    5: "Fleet (5+, logi)",
}


def normalise_min_ship(text: object, danger: int, scan_group: str | None = None) -> str:
    """Map free-text ship advice onto the controlled min-ship vocabulary."""
    raw = str(text or "").strip()
    low = raw.lower()
    if not raw:
        if scan_group in ("Data Site", "Relic Site") and danger <= 2:
            return EXPLO_FRIGATE
        if scan_group in ("Ore Anomaly", "Ore Site", "Ice Anomaly"):
            return "Venture / mining barge"
        return SHIP_VOCAB_DEFAULT.get(danger, "Unknown")
    m = re.search(r"(\d+)\s*\+?\s*(?:capsuleer|pilot|player|ship)", low)
    if "marauder" in low:
        return "Marauder / Rattlesnake"
    if re.search(r"capital|dread|titan|carrier", low):
        return "Fleet / capital ships"
    if m:
        n = int(m.group(1))
        return "Small gang (3-5)" if n <= 5 else f"Fleet ({n}+, logi)"
    if "fleet" in low or "gang" in low:
        return "Fleet (5+, logi)"
    if "hac" in low.split() or "heavy assault" in low:
        return "Battleship / HAC"
    if "battleship" in low:
        return "Battleship (Dominix/Rattlesnake/Praxis)"
    if "battlecruiser" in low:
        return "Battlecruiser (Drake/Gnosis/Myrmidon)"
    if "cruiser" in low:
        return "T1 cruiser (Vexor/Caracal/Omen/Rupture)"
    if "destroyer" in low:
        return "Destroyer"
    if re.search(r"explo|hacking|analyzer|cov-?ops|heron|probe|imicus|magnate", low):
        return EXPLO_FRIGATE
    if "frigate" in low:
        return "T1 frigate"
    if re.search(r"venture|mining|barge|procurer", low):
        return "Venture / mining barge"
    return SHIP_VOCAB_DEFAULT.get(danger, "Unknown")


# Ship tiers for the danger/min-ship consistency check (0 = non-combat hull).
_TIER_PATTERNS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"fleet|gang|marauder|capital|dreadnought|2\+ pilots|2\+ t3c", re.I), 6),
    (re.compile(r"battleship|t3c|hac|gila|stealth bomber|rattlesnake|stratios|praxis", re.I), 5),
    (re.compile(r"battlecruiser|\bbc\b|drake|gnosis", re.I), 4),
    (re.compile(r"cruiser", re.I), 3),
    (re.compile(r"destroyer", re.I), 2),
    (re.compile(r"t1 frigate|fast frigate|frigate with", re.I), 1),
]


def ship_tier(min_ship: str) -> int:
    """0 non-combat, 1 frigate, 2 destroyer, 3 cruiser, 4 battlecruiser, 5 battleship/T3C, 6 marauder/gang/fleet."""
    for pat, tier in _TIER_PATTERNS:
        if pat.search(min_ship):
            return tier
    return 0


def tier_phrase(tier: int, danger: int) -> str:
    if tier >= 6:
        return "Marauder / Rattlesnake" if danger == 5 else "Small gang (3-5) or Marauder"
    return {
        5: "Battleship / T3C",
        4: "Battlecruiser (Drake/Gnosis/Myrmidon)",
        3: "T1 cruiser (Vexor/Caracal/Omen/Rupture)",
        2: "Destroyer",
        1: "T1 frigate",
    }.get(tier, "Any ship")


def hazard_enemies(page: Mapping[str, Any]) -> str | None:
    """'No ships; <hazard>' for hacking sites whose description mentions hazards but has no NPC table."""
    desc = str(page.get("description") or "")
    hazards: list[str] = []
    for pat, label in (
        (r"sentr", "sentry towers"),
        (r"\bmine", "proximity mines"),
        (r"explod|explosi", "exploding containers"),
        (r"gas cloud|toxic", "toxic clouds"),
        (r"timer", "despawn timer"),
    ):
        if re.search(pat, desc, re.I):
            hazards.append(label)
    if hazards:
        return "No ships; " + ", ".join(hazards)
    return None
