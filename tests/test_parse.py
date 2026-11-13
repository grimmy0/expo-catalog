"""Unit tests for the wikitext parser (no network, inline snippets only)."""

from __future__ import annotations

import pytest

from scraper import parse
from scraper import systems as system_table
from scraper.parse import (
    NpcRow,
    normalise_class,
    parse_count,
    parse_kv,
    parse_npc_tables,
    parse_sleeper_rows,
    split_top_level,
    strip_markup,
)


def test_split_top_level_ignores_nested_templates_and_links():
    text = "a|{{co|red|x|y}}|[[Page|Label]]|b=1"
    assert split_top_level(text) == ["a", "{{co|red|x|y}}", "[[Page|Label]]", "b=1"]


def test_split_top_level_other_separator():
    assert split_top_level("1,2,{{t|a,b}},3", sep=",") == ["1", "2", "{{t|a,b}}", "3"]


def test_parse_count_variants():
    assert parse_count("1-2") == (1, 2)
    assert parse_count("0-1") == (0, 1)
    assert parse_count("15") == (15, 15)
    assert parse_count("6-7") == (6, 7)
    assert parse_count("2–3") == (2, 3)  # en dash
    assert parse_count("?") == (None, None)
    assert parse_count("") == (None, None)
    assert parse_count("3x") == (3, 3)
    assert parse_count("2-3x") == (2, 3)
    assert parse_count("4+") == (4, None)
    assert parse_count("5 (approx)") == (5, 5)


def test_normalise_class():
    assert normalise_class("Frigate") == ("frigate", None, True)
    assert normalise_class("Elite Frigate") == ("frigate", "elite", True)
    assert normalise_class("Commander Battleship") == ("battleship", "commander", True)
    assert normalise_class("Overseer Cruiser") == ("cruiser", "overseer", True)
    assert normalise_class("Officer Battleship") == ("battleship", "officer", True)
    assert normalise_class("Friendly Industrial") == ("industrial", None, False)
    assert normalise_class("Neutral Elite Cruiser") == ("cruiser", "elite", False)
    assert normalise_class("Elite Frigates") == ("frigate", "elite", True)
    assert normalise_class("Frigate/destroyer") == ("frigate", None, True)
    assert normalise_class("Mining Frigate") == ("frigate", None, True)
    assert normalise_class("Tower") == ("sentry", None, True)
    assert normalise_class("Sentry") == ("sentry", None, True)
    for structure in (
        "Structure",
        "Accl Gate",
        "Acceleration Gate",
        "Container",
        "Asteroid",
        "Hackable",
        "Gas Cloud",
        "Station",
        "Unknown",
    ):
        assert normalise_class(structure)[0] is None, structure


NPC_TABLE = """
== Walkthrough ==
=== First Room ===
{{NPCTableHead|Initial Defenders}}
{{NPCTableSeparator|30 km from warp-in}}
{{NPCTableRow|Sentry|1|Tower Sentry Angel I}}
{{NPCTableRow|Destroyer|2|Gistior Seizer/Trasher|ewar=TP}}
{{NPCTableSeparator|Left group (60 km away)}}
{{NPCTableRow|Commander Battlecruiser|1|Gistatis Smuggler Guard|trigger=Reinforcements}}
{{NPCTableRow|Elite Frigate|6-7|Arch Gistii Nomad|ewar=Web|point=yes}}
{{NPCTableRow|Friendly Frigate|2|Republic Fleet Rifter|ewar= Web}}
|}

{{NPCTableHead|Structures}}
{{NPCTableRow|Structure|1|Gate Security|cargo=Drops key}}
{{NPCTableRow|Accl Gate|1|Acceleration Gate|note=Locked until room is cleared}}
{{NPCTableRow|Container|6|Cargo Container|destructible=yes|drop=T1 Ammo}}
{{NPCTableRow|Asteroid|30|Plagioclase}}
{{NPCTableRow|Hackable|4|Serpentis Chemical Laboratory|cargo = Can contain BPCs}}
|}

=== Second Room ===
{{NPCTableHead}}
{{NPCTableRow|Battleship|?|Unknown Overseer}}
{{NPCTableRow|Frigate/destroyer|11|}}
|}
"""


def test_parse_npc_tables_rows_and_skips():
    rows = parse_npc_tables(NPC_TABLE)
    classes = [(r.ship_class, r.count_min, r.count_max) for r in rows]
    assert classes == [
        ("sentry", 1, 1),
        ("destroyer", 2, 2),
        ("battlecruiser", 1, 1),
        ("frigate", 6, 7),
        ("frigate", 2, 2),
        ("battleship", None, None),
        ("frigate", 11, 11),
    ]
    # Structures / gates / containers / asteroids / hackables are not NPCs.
    assert all(r.raw_class not in ("Structure", "Accl Gate", "Container", "Asteroid", "Hackable") for r in rows)
    waves = [r.wave for r in rows]
    assert waves[:5] == ["Initial Defenders"] * 5
    assert waves[5] == "Table 3"  # unnamed head falls back to its index
    assert rows[0].section == "First Room" and rows[-1].section == "Second Room"


def test_parse_npc_tables_named_args():
    rows = parse_npc_tables(NPC_TABLE)
    destroyer, commander, elite, friendly = rows[1], rows[2], rows[3], rows[4]
    assert destroyer.ewar == ["TP"]
    assert commander.tier == "commander" and commander.trigger == "Reinforcements"
    assert elite.tier == "elite" and elite.ewar == ["Web", "point"] and elite.hostile
    assert friendly.hostile is False and friendly.ewar == ["Web"]
    assert destroyer.name == "Gistior Seizer/Trasher"


CODES = {
    "apat": {"name": "Awakened Patroller", "class": "cruiser", "ewar": []},
    "awat": {"name": "Awakened Watchman", "class": "cruiser", "ewar": ["Energy Neutralization"]},
    "epat": {"name": "Emergent Patroller", "class": "frigate", "ewar": []},
    "spat": {"name": "Sleepless Patroller", "class": "battleship", "ewar": []},
    "rest": {"name": "Restless Sentry Tower", "class": "tower", "ewar": []},
}

SLEEPER = """
{{npcwh|start}}
{{npcwh|wave|Wave 1|}}
{{npcwh|apat|4x}}
{{npcwh|awat|1x|{{trigger}}}}
{{npcwh|wave|Wave 2|}}
{{npcwh|epat|2-3x}}
{{npcwh|spat|1x|{{trigger}}}}
{{npcwh|rest|2x}}
{{npcwh|bogus|9x}}
{{npcwh|end}}
"""


def test_parse_sleeper_rows():
    rows = parse_sleeper_rows(SLEEPER, CODES)
    assert [(r.wave, r.ship_class, r.count_min, r.count_max, r.name) for r in rows] == [
        ("Wave 1", "cruiser", 4, 4, "Awakened Patroller"),
        ("Wave 1", "cruiser", 1, 1, "Awakened Watchman"),
        ("Wave 2", "frigate", 2, 3, "Emergent Patroller"),
        ("Wave 2", "battleship", 1, 1, "Sleepless Patroller"),
        ("Wave 2", "sentry", 2, 2, "Restless Sentry Tower"),
    ]
    assert rows[1].trigger == "trigger" and rows[0].trigger is None
    assert rows[1].ewar == ["Energy Neutralization"]
    assert all(isinstance(r, NpcRow) for r in rows)


def test_strip_markup():
    assert (
        strip_markup("'''Angel Vigil''' is a [[combat site]] in [[High-sec|high security]]")
        == "Angel Vigil is a combat site in high security"
    )
    assert strip_markup("{{co|#9ef37c|(Faction)}} Mainframe<ref>x</ref>") == "(Faction) Mainframe"
    assert strip_markup("[[File:Icon.png|24px|link=]]Aridia<br>Curse") == "Aridia Curse"
    assert strip_markup("{{Damagetype|Th|Em}}") == "Th/Em"
    assert strip_markup("see [https://example.com here] and <!-- hidden -->text") == "see here and text"


def test_parse_kv():
    inner = (
        "|name=Angel Vigil\n|type=unrated\n| ship limit = Battlecruiser\n|faction=[[Angel "
        "Cartel|Angel]]\n|empty=\n|location=High, Low"
    )
    assert parse_kv(inner) == {
        "name": "Angel Vigil",
        "type": "unrated",
        "ship limit": "Battlecruiser",
        "faction": "Angel",
        "location": "High, Low",
    }


# --------------------------------------------------------------------------- tracked inputs
def test_tracked_inputs_exist_and_load():
    assert parse.NPCWH_FILE.is_file() and parse.WHISK_TEMPLATE.is_file() and system_table.SYSTEMS_FILE.is_file()
    assert parse.NPCWH_FILE.parent.name == "data" and parse.WHISK_TEMPLATE.parent.name == "data"
    codes = parse.load_npcwh_codes()
    assert codes and all("name" in v and "class" in v for v in codes.values())
    assert parse.load_whisk()
    systems = parse.load_systems()
    assert systems and all(isinstance(v["security"], float) and v["region"] for v in systems.values())


@pytest.mark.parametrize(
    ("module", "attr", "loader"),
    [
        (parse, "NPCWH_FILE", "load_npcwh_codes"),
        (parse, "WHISK_TEMPLATE", "load_whisk"),
        (system_table, "SYSTEMS_FILE", "load_systems"),
    ],
)
def test_missing_tracked_input_raises(monkeypatch, tmp_path, module, attr, loader):
    monkeypatch.setattr(module, attr, tmp_path / "missing")
    with pytest.raises(FileNotFoundError, match="missing"):
        getattr(parse, loader)()


# --------------------------------------------------------------------------- COSMOS pages
COURIER = """{{Missiondetails
|Name=
|Level= 4
|Type= Encounter
|Objective= Acquire 3 x Ovon Flac's Documents (0.3 m³)
|Faction1= Serpentis
|EWAR= Web (Serpentis Stasis Towers)
|ShipSizeLimit=
}}
{{MissionBriefing
|The container you delivered to me was completely empty! Those damned Serpentis must have snatched them.
}}

The Cosmic Signature of the same name is located in PPG-XC.

It is unknown if the Signature is always present or if accepting the Mission spawns the site.

{{NPCTableHead|Defenders}}
{{NPCTableRow|Battleship|5|Core Lord Admiral}}
{{NPCTableRow|Sentry|4|Serpentis Stasis Tower|ewar= Web}}
|}

<noinclude>
[[Category:COSMOS sites]]
[[Category:COSMOS missions]]
</noinclude>
"""


def test_missiondetails_is_read_as_the_infobox_without_a_site_type():
    kind, infobox = parse.parse_infobox(COURIER)
    assert kind == "Missiondetails"
    assert infobox["faction"] == "Serpentis" and infobox["level"] == "4"
    assert infobox["ewar"].startswith("Web") and infobox["mission type"] == "Encounter"
    assert "type" not in infobox  # "Encounter" must never reach the site-type rules
    assert "ship limit" not in infobox  # empty values are dropped


def test_site_infobox_wins_over_missiondetails():
    kind, infobox = parse.parse_infobox("{{CMBSiteInfo\n|type=COSMOS\n|location=Inder\n}}\n" + COURIER)
    assert kind == "CMBSiteInfo" and infobox == {"type": "COSMOS", "location": "Inder"}


@pytest.mark.parametrize(
    ("location", "text", "title", "first"),
    [
        ("", COURIER, "Courier Gone Missing (2 of 2)", "PPG-XC"),
        ("", "The Bandit Hideout is a small COSMOS combat site in Sakkikainen. It is marked", "", "Sakkikainen"),
        ("", "is a [[Minmatar COSMOS]] level 4 mission site in DUO-51 ({{ColorSecurityRating|-0.5}}).", "", "DUO-51"),
        ("", "an unnamed and unmarked site in Autama system. The site is located at Autama VII", "", "Autama"),
        ("", "Port Maphante is a static COSMOS site in system of Garisas.", "", "Garisas"),
        ("Airmia ({{ColorSecurityRating|{{SystemToSecurity|Airmia}}}})", "", "", "Airmia"),
        ("-0.8 YAW-7M (Low Sec Warning!)", "", "", "YAW-7M"),
        ("IGE-RI (Null)", "", "", "IGE-RI"),
        ("Old Man Star", "", "", "Old Man Star"),
        ("", "", "Otitoh VII- Moon 19", "Otitoh"),
    ],
)
def test_system_candidates_first_guess(location, text, title, first):
    assert parse.system_candidates(location, text, title)[0] == first


def test_system_candidates_order_and_stop_words():
    loc = "E-8CSQ constellation of the Vale of the Silent"
    cands = parse.system_candidates(loc, "")
    assert cands[0] == "E-8CSQ" and "Vale" not in cands  # Vale is a Pochven system, not meant here
    assert parse.system_candidates("-0.8 YAW-7M (Low Sec Warning!)", "") == ["YAW-7M"]
    cands = parse.system_candidates("", "A site in Amarr space, located in Hjoramold.")
    assert cands[0] == "Hjoramold" and "Amarr" not in cands
    # A misspelt link label still yields the real system from the dotlan URL.
    link = "[https://evemaps.dotlan.net/map/Derelik/Kenobanala Kenobalana]"
    assert parse.system_candidates("Kenobalana", link)[:2] == ["Kenobalana", "Kenobanala"]


@pytest.mark.parametrize(
    ("text", "infobox", "hint"),
    [
        ("", {"signature strength": "Beacon"}, "beacon"),
        ("", {"signature strength": "Signature"}, "signature"),
        ("", {"signature strength": "5% in High Sec"}, "signature"),
        ("The Cosmic Signature of the same name is located in PPG-XC.", {}, "signature"),
        ("It has no beacon and needs to be scanned with probes.", {}, "signature"),
        ("Kazka Bandit Post is a Caldari COSMOS signature (TQH-960) in Otomainen.", {}, "signature"),
        ("It is marked with a warpable beacon that is visible in the overview.", {}, "beacon"),
        ("The site shows up on overview as a beacon.", {}, "beacon"),
        ("It shows up as an Anomaly using the probe scanner. There is no requirement to probe it down.", {}, "anomaly"),
        ("Restricted Caldari Navy Base is a Guristas COSMOS combat anomaly.", {}, "anomaly"),
        ("Rush in and shoot everything.", {"signature strength": "Unknown"}, None),
    ],
)
def test_scan_hint(text, infobox, hint):
    assert parse.scan_hint(text, infobox) == hint


def test_parse_page_resolves_cosmos_system_and_hint(tmp_path):
    path = tmp_path / "Courier_Gone_Missing_2_of_2.wiki"
    path.write_text("<!-- TITLE: Courier Gone Missing (2 of 2) -->\n" + COURIER, encoding="utf-8")
    systems = {"PPG-XC": {"security": -0.0436, "region": "Cloud Ring"}}
    page = parse.parse_page(path, {}, {}, {}, systems)
    assert page.title == "Courier Gone Missing (2 of 2)"
    assert page.categories == ["COSMOS missions", "COSMOS sites"]
    assert page.infobox_kind == "Missiondetails" and page.infobox["faction"] == "Serpentis"
    assert page.system == {"name": "PPG-XC", "security": -0.0436, "region": "Cloud Ring"}
    assert page.scan_hint == "signature"
    assert page.description == "The Cosmic Signature of the same name is located in PPG-XC."
    assert [r.name for r in page.npc_rows] == ["Core Lord Admiral", "Serpentis Stasis Tower"]


def test_parse_page_leaves_non_cosmos_pages_alone(tmp_path):
    path = tmp_path / "Angel_Vigil.wiki"
    path.write_text("<!-- TITLE: Angel Vigil -->\nA site in Hjoramold.\n[[Category:Unrated Complexes]]\n")
    page = parse.parse_page(path, {}, {}, {}, {"Hjoramold": {"security": 0.5, "region": "Metropolis"}})
    assert page.system_candidates == [] and page.system is None and page.scan_hint is None
