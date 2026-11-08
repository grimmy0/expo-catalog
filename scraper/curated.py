"""Hand-curated catalog data: exclusions, merges, generated site families and overrides.

Everything the EVE University wiki does not expose as one page per in-game site
is produced here: generic pirate data/relic sites, ghost sites, faction-warfare
plexes, insurgency sites, homefront variants, Pochven ore fields, wormhole
connections (from ``data/wormholes.json``), Drifter/shattered beacons, odd ore
and ice anomalies, pirate strongholds, Singularity-only (unverified) entries and
seasonal event sites (from the event research JSON).

Each generated record is a plain dict with the ``sites`` columns (minus ``id``
and ``search_text``) plus an optional ``enemy_rows`` list.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from scraper.rules import DANGER_LABELS, EXPLO_FRIGATE, canonical_faction, normalise_min_ship, source_url

ROOT = Path(__file__).resolve().parent.parent
WORMHOLES_FILE = ROOT / "data" / "wormholes.json"
EVENTS_FILE_CANDIDATES = (
    ROOT / "data" / "event_sites.json",
    Path(
        "/tmp/claude-1000/-home-grmm-projects-expo-catalog/8109817a-86dd-4a19-b450-5201675d89c8/scratchpad/events/event_sites.json"
    ),
)

WIKI = "https://wiki.eveuniversity.org/"

# --------------------------------------------------------------------------- exclusions / merges
EXCLUDE_TITLES: frozenset[str] = frozenset(
    {
        "List of data and relic sites",
        "Relic and data sites",
        "Sleeper Cache",
        "Ghost Sites",
        "Wormhole sites",
        "Triglavian Invasion combat sites",
        "Arithmos Tyrannos",
        "Original Drifter Combat Anomalies",
        "Incursion sites",
        "Stronghold",  # replaced by the two faction strongholds below
        # Homefront base pages are replaced by their named empire variants.
        "Suspicious Signal",
        "Dread Assault",
        "Raid",
        "Emergency Aid",
        "Metaliminal Meteoroid",
        "Abyssal Artifact Recovery",
        "Salvage Research",
        "Traffic Stop",
        "Stabilize Rift",
    }
)

# "(updated)" duplicate pages whose rows should be folded into the base page.
MERGE_INTO_BASE: dict[str, str] = {
    "Quarantine Area (updated)": "Quarantine Area",
    "The Line(updated)": "The Line",
}

# Event names that already exist as wiki pages (don't duplicate from the event JSON).
EVENT_PAGE_ALIASES: dict[str, str] = {
    "Crimson Gauntlet": "Crimson Gauntlet (2020)",
    "Rampant Drone Fabricator": "Rampant Drone Fabricator",
    "Wightstorm Anchorage": "Wightstorm Anchorage",
    "Wightstorm Forward Base": "Wightstorm Forward Base",
    "Wightstorm Muster Point": "Wightstorm Muster Point",
    "Wightstorm Transit Site": "Wightstorm Transit Site",
    "Union Day Combat Challenge": "Union Day Combat Challenge",
    "Union Day Elite Combat Challenge": "Union Day Elite Combat Challenge",
    "Guri Malakim Survey Base": "Guri Malakim Survey Base",
    "SoCT Survey Expedition": "SoCT Survey Expedition",
    "Smuggler Hideout": "Smuggler Hideout",
    "Confiscated Smuggler Hideout": "Confiscated Smuggler Hideout",
    "Warp Matrix Convergence": "Warp Matrix Convergence",
}

# --------------------------------------------------------------------------- overrides (by wiki title)
OVERRIDES: dict[str, dict[str, Any]] = {
    "Rampant Drone Fabricator": {
        "min_ship": "Cruiser gang (3-5); solo possible for early waves",
        "danger": 4,
        "status": "active",
        "space": "C1-C6",
        "faction": "Rogue Drones",
        "loot_note": "Permanent in all wormhole classes since July 2026 (Version 24.01); loot only from the "
        "Fabricator.",
    },
    "Besieged Covert Research Facility": {"min_ship": "Gila / stealth bomber (kinetic)", "danger": 4},
    "SCC Secure Key Storage": {
        "min_ship": "Marauder + 2 hacking ships",
        "danger": 5,
        "faction": "CONCORD/SCC",
        "loot_note": "ESS reserve keys; 30 min hidden timer.",
    },
    "AEGIS Capital Ship Security Facility": {
        "min_ship": "Cov-ops / T1 explo frigate (T2 analyzer)",
        "danger": 3,
        "faction": "AEGIS",
        "space": "Low, Null",
        "rating": "Level III",
    },
    "Serpentis Capital Staging": {
        "danger": 5,
        "min_ship": "Battleship gang / dreadnought",
        "space": "Low, Null",
        "enemies": "Subcapital support fleet (warp-disrupting frigates) + 3 Serpentis dreadnoughts",
        "scan_group": "Combat Anomaly",
        "is_signature": 0,
        "description": "Escalation from Serpentis combat anomalies (Hidden Rally Point); three dreadnoughts, ~295M ISK "
        "bounties.",
    },
    "Drifter Hive(Barbican)": {
        "name": "Barbican",
        "danger": 5,
        "status": "unverified",
        "description": "Drifter Hive beacon in the Barbican system (J110145, now 'Liberated Barbican'). Sites were "
        "reconfigured in the 2025 Drifter crisis; composition below is the pre-crisis hive.",
    },
    "Drifter Hive Anomaly": {
        "name": "Conflux",
        "danger": 5,
        "status": "unverified",
        "description": "Drifter Hive beacon in the Conflux system (J200727, now 'Conflux Eyrie'). Sites were "
        "reconfigured in the 2025 Drifter crisis; composition below is the pre-crisis hive.",
    },
    "Deepflow rifts": {"name": "Deepflow Rift", "rating": "Level I"},
    "Jove Observatory": {
        "danger": 4,
        "enemies": "Autothysian Lancers (4-5 cruisers) and roaming Drifter battleships respond",
        "min_ship": "Any ship (stay >50 km; leave if Drifters arrive)",
        "faction": "Drifters",
        "description": "Jove Observatory beacon; Drifter wormholes (Unidentified Wormhole) only spawn in these "
        "systems.",
    },
    "Unknown Anomaly": {"name": "Unknown Anomaly (Unidentified Anomaly)", "min_ship": "Fleet (10+, logi); avoid solo"},
    "Epicenter": {"min_ship": "Cruiser / BC (Gnosis/Drake)", "danger": 3},
    "Crimson Gauntlet (2020)": {
        "name": "Crimson Gauntlet",
        "status": "event",
        "danger": 3,
        "min_ship": "Battlecruiser (Drake/Gnosis/Myrmidon)",
    },
    "Emerging Conduit": {
        "name": "Emerging Conduit (2019-2020 highsec version)",
        "status": "removed",
        "description": "The original all-highsec Emerging Conduit (Oct 2019 - May 2020) no longer exists; a revamped "
        "Emerging Conduit still spawns in Triglavian/EDENCOM minor-victory systems and Pochven.",
    },
    "Minor Conduit": {
        "description": "Harder version of the Emerging Conduit; spawns in Triglavian/EDENCOM minor-victory systems and "
        "Pochven."
    },
    "Contested Covert Research Facilities": {
        "name": "Contested Guristas Covert Research Facility",
        "status": "removed",
        "enemies": "None (exploding can, ~2000 explosive dmg)",
    },
    "Interrupted Expedition": {
        "loot_note": "Escalation from detected data/relic sites; 3 yellow + 4 red cores, no defenders."
    },
    "Emergent Ruins": {
        "loot_note": "Escalation from detected relic sites; 3 medium + 4 hard relic cans, no defenders."
    },
    "Overmind Nursery Grove": {"rating": "Level III", "is_signature": 1},
    "Observatory Infiltration": {"rating": "Level II", "ship_limit": "T1 cruisers and below (no cov-ops)"},
    "Phased Asteroid Field": {
        "status": "active",
        "rating": "Signature",
        "description": "Prismaticite mining site (Catalyst, Nov 2025); hyperspace fracture reveals the site to the "
        "whole system after half-way.",
    },
    "Asteroid Belt Remnants": {
        "name": "Asteroid Belt Remnants (Managed Asteroid Belt)",
        "description": "Veldspar anomaly in starter/career systems; renamed '<Empire> Managed Asteroid Belt' in "
        "Catalyst (Nov 2025), gated to Ventures and corvettes.",
    },
    "Hrada-Oki Bivouac": {
        "enemies": "None (trade nomads)",
        "min_ship": "Any ship",
        "danger": 1,
        "faction": "Hrada-Oki nomads (non-hostile)",
    },
    "Stellar Observation Post": {
        "status": "unverified",
        "description": "Invasion-era EDENCOM anomaly (T1 cruiser gate); current spawning in EDENCOM minor-victory "
        "systems unconfirmed.",
    },
}

# Sites that exist only as a hand-written row (no wiki page of their own).
EXTRA_SITES: list[dict[str, Any]] = []


# --------------------------------------------------------------------------- helpers
def _rec(
    name: str,
    category: str,
    scan_group: str,
    is_signature: int,
    space: str,
    danger: int,
    enemies: str,
    min_ship: str,
    *,
    faction: str | None = None,
    rating: str | None = None,
    ship_limit: str | None = None,
    ewar: str | None = None,
    status: str = "active",
    escalation: str | None = None,
    loot_note: str | None = None,
    description: str | None = None,
    source: str | None = None,
    enemy_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "category": category,
        "scan_group": scan_group,
        "is_signature": is_signature,
        "space": space,
        "faction": faction,
        "rating": rating,
        "danger": danger,
        "danger_label": DANGER_LABELS[danger],
        "enemies": enemies,
        "min_ship": min_ship,
        "ship_limit": ship_limit,
        "ewar": ewar,
        "status": status,
        "escalation": escalation,
        "loot_note": loot_note,
        "description": description,
        "source_url": source,
        "enemy_rows": enemy_rows or [],
    }


# --------------------------------------------------------------------------- 2. generic pirate data/relic sites
PIRATE_TOKENS = ("Serpentis", "Guristas", "Blood Raider", "Sansha", "Angel")
_TOKEN_FACTION = {
    "Serpentis": "Serpentis",
    "Guristas": "Guristas",
    "Blood Raider": "Blood Raiders",
    "Sansha": "Sansha's Nation",
    "Angel": "Angel Cartel",
}

# (suffix, scan difficulty, container note)
HS_DATA = [
    ("Mainframe", "I", "2 Info Shards"),
    ("Virus Test Site", "I", "2 Info Shards"),
    ("Data Processing Center", "II", "3 Info Shards"),
    ("Shattered Life-Support Unit", "II", "3 Info Shards"),
    ("Data Terminal", "III", "3 Info Shards, 1 Com Tower"),
    ("Production Installation", "III", "3 Info Shards, 1 Com Tower"),
    ("Backup Server", "IV", "3 Info Shards, 2 Com Towers"),
    ("Minor Shipyard", "IV", "3 Info Shards, 2 Com Towers"),
]
HS_RELIC = [
    ("Antiquated Outpost", "I", "3 Debris"),
    ("Excavation", "I", "3 Debris"),
    ("Crystal Quarry", "II", "4 Debris"),
    ("Solar Harvesters", "II", "4 Debris"),
    ("Explosive Debris", "III", "5 Debris"),
    ("Stone Formation", "III", "5 Debris, 1 Rubble"),
    ("Abandoned Colony", "IV", "5 Debris, 1 Rubble"),
    ("Mining Installation", "IV", "5 Debris, 1 Rubble"),
]
LS_DATA = [
    ("Data Fortress", "I", "1 Info Shard, 1 Comm Tower, 1 Mainframe"),
    ("Mainframe", "I", "1 Info Shard, 1 Comm Tower, 1 Mainframe"),
    ("Command Center", "II", "1 Info Shard, 2 Comm Towers, 1 Mainframe"),
    ("Data Processing Center", "II", "1 Info Shard, 2 Comm Towers, 1 Mainframe"),
    ("Data Mining Site", "III / IV", "1 Info Shard, 2-3 Comm Towers, 2 Mainframes"),
    ("Data Terminal", "III", "1 Info Shard, 2 Comm Towers, 2 Mainframes"),
    ("Backup Server", "IV", "2 Info Shards, 2 Comm Towers, 2 Mainframes"),
    ("Secure Server", "IV", "1 Info Shard, 3 Comm Towers, 2 Mainframes"),
]
LS_RELIC = [
    ("Excavation", "I", "1 Debris, 2 Rubble, 1 Remains"),
    ("Particle Accelerator", "I", "1 Debris, 2 Rubble, 1 Remains"),
    ("Collision Site", "II", "2 Debris, 2 Rubble, 1 Remains"),
    ("Mass Grave", "II", "1 Debris, 3 Rubble, 2 Remains"),
    ("Lone Vessel", "III", "1 Debris, 3 Rubble, 2 Remains"),
    ("Rock Formation", "III", "1 Rubble, 3 Remains, 2 Ruins"),
    ("Mining Installation", "IV", "2 Debris, 4 Rubble, 2 Remains"),
    ("Quarry", "IV", "2 Debris, 4 Rubble, 2 Remains"),
]
NS_DATA = [
    ("Sparking Transmitter", "I", "1 Comm Tower, 3 Mainframes, 1 Databank"),
    ("Survey Site", "I", "2 Comm Towers, 2 Mainframes, 2 Databanks"),
    ("Command Center", "III", "1 Comm Tower, 2 Mainframes, 3 Databanks"),
    ("Data Mining Site", "III (WH) / IV (Null)", "1 Comm Tower, 2 Mainframes, 4 Databanks"),
]
NS_RELIC = [
    ("Monument Site", "I", "2 Rubble, 3 Remains, 1 Ruins"),
    ("Temple Site", "II", "1 Rubble, 3 Remains, 2 Ruins"),
    ("Science Outpost", "III", "4 Remains, 2 Ruins"),
    ("Crystal Quarry", "III (WH) / IV (Null)", "1 Rubble, 3 Remains, 3 Ruins"),
]


def generic_hacking_sites() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    families = [
        ("Local", "data", "High", HS_DATA),
        ("Crumbling", "relic", "High", HS_RELIC),
        ("Regional", "data", "Low", LS_DATA),
        ("Decayed", "relic", "Low", LS_RELIC),
        ("Central", "data", "Null, Wormhole", NS_DATA),
        ("Ruined", "relic", "Null, Wormhole", NS_RELIC),
    ]
    for prefix, cat, space, table in families:
        for token in PIRATE_TOKENS:
            for suffix, diff, cans in table:
                analyzer = "data" if cat == "data" else "relic"
                out.append(
                    _rec(
                        f"{prefix} {token} {suffix}",
                        cat,
                        "Data Site" if cat == "data" else "Relic Site",
                        1,
                        space,
                        1,
                        "None",
                        EXPLO_FRIGATE,
                        faction=_TOKEN_FACTION[token],
                        rating=f"Scan difficulty {diff}",
                        loot_note=f"Containers: {cans}. Needs a {analyzer} analyzer.",
                        description=(
                            f"Pirate {cat} site of the local {_TOKEN_FACTION[token]} faction; no NPC defenders."
                        ),
                        source=WIKI + "List_of_data_and_relic_sites",
                    )
                )
    return out


# --------------------------------------------------------------------------- 3. ghost sites
GHOST_SIZES = [
    (
        "Lesser",
        "High",
        3,
        "Heron Navy Issue / cov-ops (MWD, explosive tank)",
        "6,000",
        "Mid-grade Ascendancy BPCs, Shattered Villard Wheels",
    ),
    (
        "Standard",
        "Low",
        3,
        "Heron Navy Issue / cov-ops (MWD, explosive tank)",
        "8,000",
        "High/Mid-grade Ascendancy BPCs, 'Wetu'/'Packrat' BPCs",
    ),
    (
        "Improved",
        "Null",
        4,
        "Cov-ops / Astero (MWD, explosive tank)",
        "10,000",
        "High-grade Ascendancy BPCs, capital construction components",
    ),
    (
        "Superior",
        "Wormhole",
        4,
        "Cov-ops / Astero (MWD, explosive tank)",
        "12,000",
        "High-grade Ascendancy BPCs, 'Magpie' MTU, capital components",
    ),
]
GHOST_FACTIONS = ("Serpentis", "Angel", "Blood Raider", "Guristas", "Sansha")


def ghost_sites() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for size, space, danger, ship, dmg, loot in GHOST_SIZES:
        for token in GHOST_FACTIONS:
            faction = _TOKEN_FACTION[token]
            disruptor = "Watcher" if token == "Angel" else "Sentry"
            out.append(
                _rec(
                    f"{size} {token} Covert Research Facility",
                    "ghost",
                    "Data Site",
                    1,
                    space,
                    danger,
                    f"Pirate response fleet (~5 {faction} ships, {disruptor} warp-disrupts) arrives on a hidden timer; "
                    f"cans explode for ~{dmg} dmg",
                    ship,
                    faction=faction,
                    rating="Ghost site",
                    ewar="point",
                    loot_note=f"Possible loot: {loot}. Shows as a Combat Site (4 AU) in the Drone regions.",
                    description=(
                        "Ghost site: hack as many of the 4 cans as possible before the timer expires, then "
                        "leave. Data analyzer only."
                    ),
                    source=WIKI + "Ghost_Sites",
                    enemy_rows=[
                        {
                            "wave": "Response fleet",
                            "ship_class": "battlecruiser",
                            "count_min": 4,
                            "count_max": 6,
                            "name": f"{faction} covert research response ships",
                            "tier": None,
                            "ewar": "point",
                        }
                    ],
                )
            )
    return out


# --------------------------------------------------------------------------- 4. faction warfare complexes
FW_EMPIRES = ("Amarr", "Caldari", "Gallente", "Minmatar")
# (suffix, size key, status)
FW_TYPES = [
    ("Scout NVY-1", "Scout", "active"),
    ("Scout NVY-2", "Scout", "active"),
    ("Scout BSC-1", "Scout", "unverified"),
    ("Small NVY-1", "Small", "active"),
    ("Small NVY-2", "Small", "active"),
    ("Small ADV-1", "Small", "active"),
    ("Small ADV-2", "Small", "active"),
    ("FRF ELT-5", "FRF", "active"),
    ("Medium NVY-1", "Medium", "active"),
    ("Medium NVY-3", "Medium", "active"),
    ("Medium ADV-1", "Medium", "active"),
    ("Medium ADV-3", "Medium", "active"),
    ("Moderate NVY-3", "Moderate", "active"),
    ("Large NVY-1", "Large", "active"),
    ("Large NVY-4", "Large", "active"),
    ("Large ADV-1", "Large", "active"),
    ("Large ADV-4", "Large", "active"),
    ("Open Complex", "Open", "active"),
    ("Battlefield", "Battlefield", "unverified"),
]
FW_SIZE = {
    # size -> (ship limit, NPC defender class, min ship, danger, capture time)
    "Scout": ("Frigates and smaller", "frigate", "T1 frigate", 2, "10 min (5 min BSC)"),
    "Small": ("Destroyers and smaller", "destroyer", "Destroyer (T1/Navy)", 2, "10 min"),
    "FRF": ("Frigates (ELT: T1/T2/T3 incl. T3 destroyers)", "frigate", "Destroyer (T1/Navy)", 2, "10 min"),
    "Medium": ("Cruisers and smaller", "cruiser", "T1 cruiser", 2, "15 min"),
    "Moderate": ("Battlecruisers and smaller", "cruiser", "Battlecruiser", 3, "15 min"),
    "Large": ("Battleships and smaller", "battlecruiser", "Battleship", 3, "15 min"),
    "Open": ("Unrestricted (no gate)", "battlecruiser", "Any (BC+ recommended)", 3, "15 min"),
    "Battlefield": ("T1 and Navy ships", "battlecruiser", "Fleet (10+, T1/Navy hulls)", 3, "three capture points"),
}
_TIER_NOTE = {
    "BSC": "Basic: T1 combat hulls only",
    "NVY": "Navy: T1 and Navy hulls",
    "ADV": "Advanced: T2 and pirate hulls (some T3)",
    "ELT": "Elite: T1/T2/T3 with T3 bonuses",
}


def fw_complexes() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for empire in FW_EMPIRES:
        for suffix, size, status in FW_TYPES:
            limit, defender, ship, danger, capture = FW_SIZE[size]
            tier = next((t for t in _TIER_NOTE if t in suffix), None)
            note = _TIER_NOTE.get(tier or "", "")
            enemies = (
                f"2-5 {empire} Navy {defender}s (respawn 1.5-5 min)"
                if size != "Battlefield"
                else f"{empire} Navy NPC fleet around three capture points"
            )
            out.append(
                _rec(
                    f"{empire} {suffix}",
                    "fw_complex",
                    "Combat Anomaly",
                    0,
                    "Low (FW warzone)",
                    danger,
                    enemies,
                    ship,
                    faction=f"{empire} Navy",
                    rating=f"{size} plex",
                    ship_limit=limit,
                    status=status,
                    loot_note=f"Capture timer {capture}. {note}".strip(),
                    description=(
                        f"Faction warfare complex in {empire}-held warzone systems; capture by holding the "
                        f"button with no enemies within 30 km."
                    ),
                    source=WIKI + "Faction_warfare#Complexes",
                    enemy_rows=[
                        {
                            "wave": "Defenders",
                            "ship_class": defender,
                            "count_min": 2,
                            "count_max": 5,
                            "name": f"{empire} Navy {defender}",
                            "tier": None,
                            "ewar": None,
                        }
                    ],
                )
            )
    return out


# --------------------------------------------------------------------------- 5. insurgency
INSURGENCY_RAIDS = [
    (
        "Small Outpost Raid ADV-1",
        "Destroyers and smaller (T1/Navy/pirate/T2)",
        "Destroyer (T1/Navy)",
        2,
        "1-2 players, 10 min",
    ),
    ("Medium Outpost Raid ADV-5", "Cruisers and smaller + T3 destroyers", "T1 cruiser", 3, "1-5 players, 15 min"),
    (
        "Moderate Outpost Raid ADV-3",
        "Battlecruisers and smaller + T3 destroyers",
        "Battlecruiser",
        3,
        "1-3 players, 15 min",
    ),
    ("Large Outpost Raid ADV-5", "Battleships and smaller", "Battleship", 3, "1-5 players, 15 min"),
]


def insurgency_sites() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for pirate, faction in (("Guristas", "Guristas"), ("Angel", "Angel Cartel")):
        for suffix, limit, ship, danger, note in INSURGENCY_RAIDS:
            out.append(
                _rec(
                    f"{pirate} {suffix}",
                    "insurgency",
                    "Combat Anomaly",
                    0,
                    "Low, High (insurgency systems)",
                    danger,
                    f"Mordu's Legion defenders (vs pirates) or {faction} defenders (vs empire), 2-5 ships",
                    ship,
                    faction=f"Mordu's Legion / {faction}",
                    rating="Corporate Outpost Raid",
                    ship_limit=limit,
                    loot_note=note,
                    source=WIKI + "Insurgency",
                    description=(
                        "Insurgency complex; capture adds Corruption (pirate militia) or Suppression (empire militia)."
                    ),
                )
            )
    out.append(
        _rec(
            "Mining Op Ambush",
            "insurgency",
            "Combat Anomaly",
            0,
            "Low, High (insurgency systems, corruption 1+)",
            3,
            "Pirate NPC tacklers on an ORE Rorqual, then Mordu's Legion mercenary waves (neuts, scrams, points)",
            "T1 cruiser (well fit)",
            faction="Mordu's Legion",
            rating="Open site",
            ship_limit="Unrestricted",
            ewar="scram, point, neut",
            loot_note="LP shared up to 5 players.",
            source=WIKI + "Insurgency",
        )
    )
    out.append(
        _rec(
            "Ice Refinery Heist",
            "insurgency",
            "Combat Anomaly",
            0,
            "Low (insurgency systems, corruption 3-4)",
            4,
            "Repeated NPC waves (full damage) plus Upwell Thunderchild guards; escort 10 tankers",
            "Fleet (5+, logi)",
            faction="Upwell / Mordu's Legion",
            rating="Deadspace, 5-30 players",
            loot_note="150,000 LP base, 4 h respawn.",
            source=WIKI + "Insurgency",
        )
    )
    out.append(
        _rec(
            "Pirate Laundering Facility",
            "other",
            "Beacon",
            0,
            "Low (pirate FOB system)",
            1,
            "None",
            "Any ship",
            faction="Guristas / Angel Cartel",
            loot_note="Turn in named-NPC loot for reward crates (pirate militia).",
            source=WIKI + "Insurgency",
        )
    )
    out.append(
        _rec(
            "Counter-Insurgency Outpost",
            "other",
            "Beacon",
            0,
            "War HQ systems (Mehatoor, Onnamon, Intaki, Amo)",
            1,
            "None",
            "Any ship",
            faction="Empire navies",
            loot_note="Turn in named-NPC loot for reward crates (empire militia).",
            source=WIKI + "Insurgency",
        )
    )
    return out


# --------------------------------------------------------------------------- 6. homefront operations
HOMEFRONT_VARIANTS: list[tuple[str, str, str, str, int]] = [
    # (name, base page, enemy faction, ewar, pilots)
    ("Suspicious Signal: Secure the Intel", "Suspicious Signal", "Minmatar Republic", "tp", 5),
    ("Suspicious Signal: Block the Broadcast", "Suspicious Signal", "Gallente Federation", "damp", 5),
    ("Suspicious Signal: Stop the Siphon", "Suspicious Signal", "Caldari State", "ecm", 5),
    ("Suspicious Signal: Stop the Sabotage", "Suspicious Signal", "Amarr Empire", "neut, td", 5),
    ("Dread Assault: Blood Raider Temple", "Dread Assault", "Blood Raiders", "neut, td, ecm", 5),
    ("Dread Assault: Occupied Industry", "Dread Assault", "United Champions of Freedom", "neut, ecm", 5),
    ("Dread Assault: Primacy Base", "Dread Assault", "Gallentia Primacy", "neut, ecm", 5),
    ("Dread Assault: Cartel Racket", "Dread Assault", "Angel Cartel", "tp, ecm", 5),
    ("Raid: Hall of Sacrifice", "Raid", "Blood Raiders", "neut, td", 5),
    ("Raid: Black Market", "Raid", "Guristas", "ecm", 5),
    ("Raid: Narcotics Lab", "Raid", "Serpentis", "damp", 5),
    ("Raid: Deserters Hideout", "Raid", "Ashes of Turnur", "ecm", 5),
    ("Emergency Aid: Holy Mission", "Emergency Aid", "Disciples of Purity", "ecm", 5),
    ("Emergency Aid: Convoy", "Emergency Aid", "Guristas", "ecm", 5),
    ("Emergency Aid: Automated Factory", "Emergency Aid", "Rogue Drones", "web", 5),
    ("Emergency Aid: Clan Holding", "Emergency Aid", "Angel Cartel", "tp", 5),
    ("Metaliminal Meteoroid: Amarr Mining", "Metaliminal Meteoroid", "Disciples of Purity", "ecm", 5),
    ("Metaliminal Meteoroid: Caldari Mining", "Metaliminal Meteoroid", "Guristas", "ecm", 5),
    ("Metaliminal Meteoroid: Gallente Mining", "Metaliminal Meteoroid", "Rogue Drones", "web", 5),
    ("Metaliminal Meteoroid: Minmatar Mining", "Metaliminal Meteoroid", "Ashes of Turnur", "ecm", 5),
    (
        "Abyssal Artifact Recovery",
        "Abyssal Artifact Recovery",
        "Triglavian Collective",
        "bubble, neut, td, web, tp, damp",
        5,
    ),
    ("Salvage Research", "Salvage Research", "Ashes of Turnur", "ecm", 3),
    ("Traffic Stop", "Traffic Stop", "Varies by empire", None, 3),
    ("Stabilize Rift", "Stabilize Rift", "Sleepers", "neut", 3),
]
_HF_ROLE = {
    "Suspicious Signal": "Hack and defend data nodes against the rival empire's navy.",
    "Dread Assault": "Destroy a dreadnought-class target under heavy neut pressure.",
    "Raid": "Tackle and kill fleeing haulers, deliver 4 cargo loads to the friendly freighter within 20 minutes.",
    "Emergency Aid": "Repair friendly structures/ships with remote repairers while under attack.",
    "Metaliminal Meteoroid": "Mine a meteoroid with a mining fleet while hostiles attack.",
    "Abyssal Artifact Recovery": "Recover artifacts from Triglavian-held space under warp-bubble and EWAR pressure.",
    "Salvage Research": "Salvage wrecks under fire (3-pilot operation).",
    "Traffic Stop": "Cargo-scan and tackle smugglers (3-pilot operation).",
    "Stabilize Rift": "Stabilise an abyssal rift against Sleepers using capacitor transfers (3-pilot operation).",
}


def homefront_sites(pages: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, base, enemy, ewar, pilots in HOMEFRONT_VARIANTS:
        page = pages.get(base, {})
        desc = str(page.get("description") or "") or _HF_ROLE.get(base, "")
        out.append(
            _rec(
                name,
                "homefront",
                "Combat Anomaly",
                0,
                "High",
                4,
                f"Hostile {enemy} fleet sized for {pilots} T1 cruisers (frigate-battlecruiser waves)",
                f"Fleet of {pilots} T1 cruisers + logi",
                faction=enemy,
                rating=f"Homefront ({pilots} pilots)",
                ship_limit="T1 / Navy / pirate hulls up to cruiser (gate-restricted)",
                ewar=ewar,
                description=(_HF_ROLE.get(base, "") + " " + desc).strip()[:600],
                source=source_url(base),
            )
        )
    return out


# --------------------------------------------------------------------------- 7. Pochven ore fields
def pochven_ore_fields() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    zones = [
        ("Border", "lowest-grade ores"),
        ("Internal", "moderate-grade ores"),
        ("Home", "best ores incl. II/III grades"),
    ]
    for zone, quality in zones:
        ores = ["Bezdnacine", "Rakovene", "Talassonite", "Spodumain"] + (["Mercoxit"] if zone == "Home" else [])
        for ore in ores:
            out.append(
                _rec(
                    f"{zone} {ore} Field",
                    "ore",
                    "Ore Anomaly",
                    0,
                    f"Pochven ({zone.lower()} systems)",
                    2,
                    "None on arrival; roaming EDENCOM/Triglavian/Rogue Drone/Sleeper/Drifter fleets warp to ore sites",
                    "Procurer / Venture (roaming NPC fleets)",
                    faction="Triglavian Collective (roamers)",
                    rating=quality,
                    loot_note="Pochven ores contain every mineral except Mexallon and Pyerite.",
                    description="Pochven ore anomaly; Home systems may also spawn Mercoxit.",
                    source=WIKI + "Pochven",
                )
            )
    return out


# --------------------------------------------------------------------------- 8. wormhole connections
_ORIGIN_BLOCKS: dict[str, tuple[str, ...]] = {
    "K-space (High, Low, Null)": (
        "Z971",
        "R943",
        "X702",
        "O128",
        "N432",
        "M555",
        "B041",
        "U319",
        "B449",
        "N944",
        "S199",
        "A641",
        "R051",
        "V283",
    ),
    "C1": ("H121", "C125", "O883", "M609", "L614", "S804", "N110", "J244", "Z060"),
    "C2": ("Z647", "D382", "O477", "Y683", "N062", "R474", "B274", "A239", "E545"),
    "C3": ("V301", "I182", "N968", "T405", "N770", "A982", "S047", "U210", "K346"),
    "C4": ("P060", "N766", "C247", "X877", "H900", "U574", "D845", "N290", "K329"),
    "C5": ("Y790", "D364", "M267", "E175", "H296", "V753", "D792", "C140", "Z142"),
    "C6": ("Q317", "G024", "L477", "Z457", "V911", "W237", "B520", "C391", "C248"),
    "Any (small-ship wormhole)": ("E004", "L005", "Z006", "M001", "C008", "G008", "Q003", "A009"),
    "Thera": ("Q063", "V898", "E587"),
    "K-space (Jove Observatory systems)": ("S877", "B735", "V928", "C414", "R259"),
    "Pochven": ("C729", "X450", "R081", "I078", "L687", "O546"),
    "Wormhole C2-C6": ("F216",),
    "Null (Drone regions)": ("U372",),
    "Various": ("T458", "M164", "L031", "F353", "F135", "J377", "J492", "R327", "O753"),
    "Any (exit side of an opened wormhole)": ("K162",),
}
_ORIGIN = {code: where for where, codes in _ORIGIN_BLOCKS.items() for code in codes}
DRIFTER_CODES = {"S877": "Sentinel", "B735": "Barbican", "V928": "Vidette", "C414": "Conflux", "R259": "Redoubt"}
POCHVEN_CODES = {"C729", "X450", "R081", "F216", "U372", "I078", "L687", "O546", "R327", "O753"}


def _jump_phrase(jump: float | None) -> str:
    if jump is None:
        return "depends on the other side"
    if jump <= 5e6:
        return "frigate/destroyer hulls (5M kg)"
    if jump <= 62e6:
        return "up to battlecruiser (62M kg)"
    if jump <= 410e6:
        return f"up to battleship ({int(jump / 1e6)}M kg)"
    return f"capital-capable ({jump / 1e9:g}B kg)"


def wormhole_connections(path: Path = WORMHOLES_FILE) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    for w in data:
        code = str(w.get("code") or w.get("name", "").replace("Wormhole ", ""))
        target = str(w.get("target") or "Unknown")
        if code == "C729":
            target = "K-space exit (High, Low or Null)"
        life = w.get("lifetime_h")
        mass = w.get("max_mass_kg")
        jump = w.get("max_jump_mass_kg")
        origin = _ORIGIN.get(code, "Various")
        desc = f"Leads to {target}."
        if life:
            desc += f" Lifetime {life:g} h."
        desc += f" Max jump mass: {_jump_phrase(jump)}."
        if mass:
            desc += f" Max total mass {mass / 1e9:g}B kg."
        if w.get("regen_kg"):
            desc += " Mass regenerates (small-ship wormhole)."
        danger, enemies, ship = 0, "None", "Any ship within the mass limit"
        if code in DRIFTER_CODES:
            danger = 5
            enemies = (
                "Drifter battleships (Apollo/Artemis Tyrannos, doomsday) patrol the K-space 'Unidentified "
                "Wormhole' beacon"
            )
            ship = "Cloaky / fast ship; avoid Drifter patrols"
        elif code in POCHVEN_CODES:
            danger = 4
            enemies = (
                "Multiple waves of guards on the Pochven side (Triglavian, EDENCOM, Rogue Drone, Sleeper or Drifter)"
            )
            ship = "Battleship gang or cloaky scout; clear with several pilots"
        name = f"Wormhole {code}"
        if code in DRIFTER_CODES:
            name += f" ({DRIFTER_CODES[code]})"
        rating = "K162 (exit)" if code == "K162" else f"→ {target}"
        out.append(
            _rec(
                name,
                "wormhole_connection",
                "Wormhole",
                1,
                origin,
                danger,
                enemies,
                ship,
                faction="Drifters"
                if code in DRIFTER_CODES
                else ("Triglavian Collective / EDENCOM" if code in POCHVEN_CODES else None),
                rating=rating,
                ship_limit=_jump_phrase(jump),
                description=desc,
                source="https://ref-data.everef.net/types/{}".format(w.get("type_id")),
            )
        )
    return out


# --------------------------------------------------------------------------- 9. Drifter / shattered / Thera
ORIGINAL_DRIFTER_ANOMALIES = {
    "Vidette": [
        "Ship Graveyard",
        "Sleeper Engineering Station",
        "Spatial Rift",
        "Sleeper Enclave in Coral Rock",
        "Crystals and Stone Circle",
    ],
    "Redoubt": ["Ship Graveyard", "Caged Wormhole", "Spatial Rift Generator", "Sleeper Enclave", "Hollow Asteroid"],
    "Sentinel": [
        "Monolith",
        "Wormhole in Rock Circle",
        "Opposing Spatial Rifts",
        "Sleeper Enclave Debris",
        "Crystal Resource",
    ],
    "Barbican": ["Wrecked Ships", "Unstable Wormhole", "Spatial Rift", "Heavily Guarded Spatial Rift", "Crystals"],
    "Conflux": [
        "Monolith",
        "Caged Wormhole",
        "Rock Formation and Wormhole",
        "Particle Acceleration Array",
        "Guarded Asteroid Station",
    ],
}
DRIFTER_SYSTEMS = {
    "Vidette": "J164710 (Sanctified Vidette, Magnetar)",
    "Redoubt": "J174618 (Azdaja Redoubt, Wolf-Rayet)",
    "Sentinel": "J055520 (Sentinel MZ, Red Giant)",
    "Barbican": "J110145 (Liberated Barbican, Cataclysmic Variable)",
    "Conflux": "J200727 (Conflux Eyrie, Pulsar)",
}


def drifter_and_shattered() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    out.append(
        _rec(
            "Unidentified Wormhole",
            "drifter",
            "Beacon",
            0,
            "High, Low, Null (Jove Observatory systems)",
            5,
            "Drifter battleships (Apollo/Artemis Tyrannos, doomsday, 500 km point) and Autothysian Lancers patrol the "
            "beacon",
            "Cloaky / fast ship (MWD); do not warp to 0",
            faction="Drifters",
            ewar="web, point, neut",
            description=(
                "K-space beacon marking a wormhole into one of the five Drifter hive systems; the hole is "
                "deadspaced 80 km from the beacon."
            ),
            source=WIKI + "Drifters",
            enemy_rows=[
                {
                    "wave": "Patrol",
                    "ship_class": "battleship",
                    "count_min": 1,
                    "count_max": 2,
                    "name": "Apollo/Artemis Tyrannos",
                    "tier": None,
                    "ewar": "web, point, neut",
                },
                {
                    "wave": "Patrol",
                    "ship_class": "cruiser",
                    "count_min": 2,
                    "count_max": 5,
                    "name": "Autothysian Lancer",
                    "tier": None,
                    "ewar": None,
                },
            ],
        )
    )
    for hive in ("Vidette", "Redoubt", "Sentinel"):
        out.append(
            _rec(
                hive,
                "drifter",
                "Beacon",
                0,
                f"Drifter wormhole {DRIFTER_SYSTEMS[hive]}",
                5,
                "Sleeper frigates/cruisers/battleships in gated rooms plus Hikanta Tyrannos Drifter battleship and "
                "wandering Drifter patrols",
                "Fleet (20-30, logi, tracking disruptors)",
                faction="Drifters",
                status="unverified",
                description=(
                    "Drifter Hive beacon; sites were reconfigured in the 2025 Drifter crisis and current "
                    "layout is undocumented."
                ),
                source=WIKI + "Drifters",
            )
        )
    for hive, names in ORIGINAL_DRIFTER_ANOMALIES.items():
        for n in names:
            out.append(
                _rec(
                    f"{n} ({hive})",
                    "drifter",
                    "Combat Anomaly",
                    0,
                    f"Drifter wormhole {DRIFTER_SYSTEMS[hive]}",
                    5,
                    "Drifter patrols (Apollo/Artemis Tyrannos battleships, Autothysian Lancers) and Sleepers",
                    "Fleet (20-30, logi)",
                    faction="Drifters",
                    status="removed",
                    description=(
                        "Original Drifter-system combat anomaly; removed and replaced during the 2025 Attack "
                        "on the Hives."
                    ),
                    source=WIKI + "Original_Drifter_Combat_Anomalies",
                )
            )
    out.append(
        _rec(
            "Labyrinth Complex",
            "drifter",
            "Combat Anomaly",
            0,
            "Drifter wormholes",
            5,
            "Randomised maze rooms with Drifters arriving through temporary wormholes",
            "Fleet (10+, logi)",
            faction="Drifters",
            status="removed",
            description="Capsuleer Day 2025 Drifter-crisis site; dropped ciphers for the Nexus Point.",
            source=WIKI + "Drifters",
        )
    )
    out.append(
        _rec(
            "Nexus Point",
            "drifter",
            "Combat Anomaly",
            0,
            "Drifter wormholes",
            5,
            "Drifter dreadnought in a single room",
            "Fleet (20+, logi)",
            faction="Drifters",
            status="removed",
            description="Capsuleer Day 2025 Drifter-crisis site, entered with a cipher from the Labyrinth Complex.",
            source=WIKI + "Drifters",
        )
    )
    out.append(
        _rec(
            "Silent Battleground",
            "relic",
            "Relic Site",
            1,
            "Shattered wormholes",
            1,
            "None",
            EXPLO_FRIGATE,
            faction="Sleepers",
            rating="Hard scan",
            loot_note=(
                "~40 data + relic cans (datacores, T3 components, ~200M ISK, ~500 m3); site despawns on a "
                "timer that starts when uncloaked."
            ),
            description="Rare shattered-system signature around a wrecked Revenant; no Sleeper defenders.",
            source=WIKI + "Shattered_wormhole_systems",
        )
    )
    return out


# --------------------------------------------------------------------------- 10. misc ore / ice
def misc_ore_ice() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name in ("Thick Blue Ice Belt", "Smooth Glacial Mass Belt"):
        out.append(
            _rec(
                name,
                "ice",
                "Ice Anomaly",
                0,
                "Null",
                1,
                "None (normal belt rats may spawn)",
                "Endurance / mining barge",
                rating="Ice belt",
                description=(
                    "Null-sec ice anomaly (Gelidus, Krystallos and the faction ice); respawns 6 h after "
                    "being mined out."
                ),
                source=WIKI + "Ice_harvesting",
            )
        )
    for name, space, note in (
        ("Small Bistot Deposit", "Null", "Pre-Equinox null-sec Bistot anomaly."),
        ("Average Bistot Deposit", "Null", "Pre-Equinox null-sec Bistot anomaly."),
        (
            "Small Mordunium Deposit",
            "High (0.5 bordering low), Null (sov hub)",
            "Pyerite Prospecting Array tier 1; also rare in 0.5 systems bordering lowsec.",
        ),
        ("Large Nocxite Deposit", "Null (sov hub upgrade)", "Nocxium Prospecting Array tier 3, 10 h respawn."),
        (
            "Large Potent Asteroid Cluster",
            "Null (sov hub upgrade)",
            "Potent variant of the Ore Prospecting Array cluster.",
        ),
        (
            "Enormous Potent Asteroid Cluster",
            "Null (sov hub upgrade)",
            "Potent variant of the Ore Prospecting Array cluster.",
        ),
        (
            "Colossal Potent Asteroid Cluster",
            "Null (sov hub upgrade)",
            "Potent variant of the Ore Prospecting Array cluster.",
        ),
    ):
        out.append(
            _rec(
                name,
                "ore",
                "Ore Anomaly",
                0,
                space,
                1,
                "None (normal belt rats may spawn)",
                "Venture",
                rating="Ore anomaly",
                description=note,
                source=WIKI + "Asteroids_and_ore",
            )
        )
    for empire, name, status in (
        ("Minmatar", "Republic Managed Asteroid Belt", "active"),
        ("Amarr", "Imperial Managed Asteroid Belt", "unverified"),
        ("Caldari", "State Managed Asteroid Belt", "unverified"),
        ("Gallente", "Federal Managed Asteroid Belt", "unverified"),
    ):
        out.append(
            _rec(
                name,
                "ore",
                "Ore Anomaly",
                0,
                f"High ({empire} starter systems)",
                1,
                "None",
                "Venture / corvette",
                rating="Ore anomaly",
                ship_limit="Basic Ventures and corvettes",
                status=status,
                description=(
                    "Catalyst (Nov 2025) replacement for Asteroid Belt Remnants: one gated Veldspar belt per "
                    "starter/career system."
                ),
                source=WIKI + "Asteroid_Belt_Remnants",
            )
        )
    return out


# --------------------------------------------------------------------------- 12. strongholds
def strongholds() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, faction, space in (
        ("Guristas Stronghold", "Guristas", "Low (Caldari and Gallente regions)"),
        ("Blood Raider Stronghold", "Blood Raiders", "Low (Amarr and Minmatar regions)"),
    ):
        out.append(
            _rec(
                name,
                "other",
                "Beacon",
                0,
                space,
                5,
                "Stronghold structure (neuts, 300 km web, ECM/damps) plus scaling diamond-NPC response fleets up to "
                "battleships",
                "Fleet (10+, logi)",
                faction=faction,
                rating="Pirate stronghold",
                ewar="web, neut, ecm, damp",
                description=(
                    "Pirate fleet staging structure; launches NPC mining ops and attacks player structures. "
                    "No longer spawns in high-sec since Catalyst (Nov 2025)."
                ),
                source=WIKI + "Stronghold",
            )
        )
    return out


# --------------------------------------------------------------------------- 13. unverified (Singularity-only)
SINGULARITY_ONLY = [
    ("Infested Research Facility", "Rogue Drones"),
    ("Infested Research Archive", "Rogue Drones"),
    ("Infestation Rendezvous Cluster", "Rogue Drones"),
    ("Rogue Drone Outbreak", "Rogue Drones"),
    ("Surveillance Vault", None),
    ("SARO Surveillance Vault (Lowsec)", "CONCORD/SCC"),
    ("Expedition Distress Signal", None),
    ("Rogue Hoard", "Rogue Drones"),
    ("Rogue Trove", "Rogue Drones"),
    ("Rogue Stockpile", "Rogue Drones"),
]


def unverified_sites() -> list[dict[str, Any]]:
    return [
        _rec(
            name,
            "other",
            "Combat Site",
            1,
            "Unknown",
            0,
            "Unknown",
            "Unknown",
            faction=faction,
            status="unverified",
            description=(
                "Seen only in Singularity test-server data (Hoboleaks build 3678022); not confirmed on "
                "Tranquility as of 2026-11-08."
            ),
            source="https://hoboleaks.space/",
        )
        for name, faction in SINGULARITY_ONLY
    ]


# --------------------------------------------------------------------------- 14. events
_KIND_MAP = {
    "combat_anomaly": ("event", "Combat Anomaly", 0),
    "data_site": ("event", "Data Site", 1),
    "relic_site": ("event", "Relic Site", 1),
    "ore_site": ("event", "Ore Anomaly", 0),
    "gas_site": ("event", "Gas Site", 1),
    "other": ("event", "Beacon", 0),
}
_STATUS_MAP = {"recurring": "event", "permanent": "active", "one-off": "removed", "unknown": "event"}


EVENT_SPACE_FIX: dict[str, str] = {
    "Limited Mining Expedition": "High, Low, Null (Stargate Trailblazers constellations)",
    "Minor Mining Expedition": "High, Low, Null (Stargate Trailblazers constellations)",
    "Standard Mining Expedition": "High, Low, Null (Stargate Trailblazers constellations)",
    "Major Mining Expedition": "High, Low, Null (Stargate Trailblazers constellations)",
    "Critical Mining Expedition": "High, Low, Null (Stargate Trailblazers constellations)",
    "Tetrimon Garrison": "Escalation (High, Low, Null)",
    "Crimson Harvest Sanctuary": "Escalation (High, Low, Null)",
    "Serpentis Shipyard": "High, Low, Null",
    "Serpentis Research Facility": "High, Low, Null",
    "Serpentis Mobilization Point": "High, Low, Null",
    "Serpentis Information Relay": "High, Low, Null",
    "Serpentis Transportation Facility": "High, Low, Null",
    "Serpentis Sortie": "High, Low, Null",
    "Angel Cartel Assembly Plant": "High, Low, Null",
    "Angel Cartel Research Bunker": "High, Low, Null",
    "Angel Cartel Mining Outpost": "High, Low, Null",
    "Angel Sortie": "High, Low, Null",
    "Union Day Hacking Challenge": "High, Low (Caldari space)",
    "Unsanctioned Labor Camp": "High, Low (Amarr, Khanid, Ammatar space)",
    "Nemesis Command Outpost": "High (Avalon Investigations systems)",
    "Yoiul Festival Snowball Exchange": "Selected systems (beacon)",
}


def _clean_faction(raw: object) -> str | None:
    return canonical_faction(raw)


def _advice_note(entry: Mapping[str, Any]) -> str | None:
    """Keep the researcher's free-text ship advice and notes in loot_note so nothing is lost."""
    parts: list[str] = []
    if entry.get("recommended_ship"):
        parts.append(f"Ship advice: {str(entry['recommended_ship']).strip()}")
    if entry.get("notes"):
        parts.append(str(entry["notes"]).strip())
    text = " | ".join(parts)
    return text[:500] or None


def _event_space(raw: str | None) -> str:
    text = (raw or "").lower()
    parts = []
    if "high" in text:
        parts.append("High")
    if "low" in text:
        parts.append("Low")
    if "null" in text:
        parts.append("Null")
    if "wormhole" in text or "w-space" in text:
        parts.append("Wormhole")
    if "pochven" in text:
        parts.append("Pochven")
    if "all" in text and not parts:
        parts = ["High", "Low", "Null"]
    return ", ".join(parts) if parts else "Unknown"


def _event_min_ship(entry: Mapping[str, Any], danger: int, scan_group: str) -> str:
    return normalise_min_ship(entry.get("recommended_ship"), danger, scan_group)


def load_events() -> list[dict[str, Any]]:
    for candidate in EVENTS_FILE_CANDIDATES:
        if candidate.exists():
            return json.loads(candidate.read_text(encoding="utf-8"))
    return []


def event_sites(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in events:
        name = str(e.get("name", "")).strip()
        if not name or name in EVENT_PAGE_ALIASES:
            continue
        category, scan_group, is_sig = _KIND_MAP.get(str(e.get("kind")), ("event", "Combat Anomaly", 0))
        danger = int(e.get("danger") or 0)
        danger = max(0, min(5, danger))
        status = _STATUS_MAP.get(str(e.get("status")), "event")
        if e.get("name_uncertain"):
            status = "unverified"
        years = e.get("years") or []
        ev = str(e.get("event") or "")
        rating = (f"{ev} " if ev else "") + (
            f"({years[0]}-{years[-1]})" if len(years) > 1 else f"({years[0]})" if years else ""
        )
        src = str(e.get("source") or "").split(";")[0].strip()
        out.append(
            _rec(
                name,
                category,
                scan_group,
                is_sig,
                EVENT_SPACE_FIX.get(name) or _event_space(e.get("space")),
                danger,
                (str(e.get("enemies") or "Unknown"))[:400],
                _event_min_ship(e, danger, scan_group),
                faction=_clean_faction(e.get("faction")),
                rating=rating.strip() or None,
                ship_limit=(str(e.get("ship_limit"))[:120] if e.get("ship_limit") else None),
                status=status,
                loot_note=_advice_note(e),
                description=f"Event site ({ev}). {e.get('danger_note') or ''}".strip(),
                source=source_url(src) if src else None,
            )
        )
    return out


def event_overrides(events: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Field overrides for event sites that already exist as wiki pages."""
    out: dict[str, dict[str, Any]] = {}
    for e in events:
        name = str(e.get("name", ""))
        title = EVENT_PAGE_ALIASES.get(name)
        if not title:
            continue
        fields: dict[str, Any] = {}
        danger = max(0, min(5, int(e.get("danger") or 0)))
        if danger:
            fields["danger"] = danger
        if e.get("recommended_ship"):
            fields["min_ship"] = normalise_min_ship(e["recommended_ship"], danger or 3)
        if _clean_faction(e.get("faction")):
            fields["faction"] = _clean_faction(e.get("faction"))
        if _advice_note(e):
            fields["loot_note"] = _advice_note(e)
        status = _STATUS_MAP.get(str(e.get("status")), "event")
        fields["status"] = status
        out[title] = fields
    # Rampant Drone Fabricator is permanent content now; keep the curated override authoritative.
    out.pop("Rampant Drone Fabricator", None)
    return out


# --------------------------------------------------------------------------- all together
def generated_sites(
    pages: Mapping[str, Mapping[str, Any]], events: Iterable[Mapping[str, Any]] | None = None
) -> list[dict[str, Any]]:
    events = list(events) if events is not None else load_events()
    out: list[dict[str, Any]] = []
    out += generic_hacking_sites()
    out += ghost_sites()
    out += fw_complexes()
    out += insurgency_sites()
    out += homefront_sites(pages)
    out += pochven_ore_fields()
    out += wormhole_connections()
    out += drifter_and_shattered()
    out += misc_ore_ice()
    out += strongholds()
    out += unverified_sites()
    out += event_sites(events)
    out += minor_victory_extras()
    return out


def minor_victory_extras() -> list[dict[str, Any]]:
    """Current (post-2020) Emerging Conduit, which the wiki only documents in its removed highsec form."""
    return [
        _rec(
            "Emerging Conduit",
            "pochven",
            "Combat Anomaly",
            0,
            "Triglavian/EDENCOM minor-victory systems; Pochven",
            3,
            "Three Triglavian waves of frigates/destroyers (Damavik, Kikimora) with a Zorya's Vedmak cruiser boss; "
            "webs, neuts, TDs",
            "Battleship (Praxis) solo or cruiser gang",
            faction="Triglavian Collective",
            ewar="web, neut, td, tp",
            description=(
                "Revamped Emerging Conduit introduced May 2020; appears as a combat anomaly in "
                "Triglavian/EDENCOM minor-victory systems and Pochven. "
                "The 2019-2020 all-highsec version is listed separately as removed."
            ),
            source=WIKI + "Emerging_Conduit",
        )
    ]
