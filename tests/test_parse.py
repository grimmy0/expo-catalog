"""Unit tests for the wikitext parser (no network, inline snippets only)."""

from __future__ import annotations

import pytest

from scraper import parse
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
    assert parse.NPCWH_FILE.is_file() and parse.WHISK_TEMPLATE.is_file()
    assert parse.NPCWH_FILE.parent.name == "data" and parse.WHISK_TEMPLATE.parent.name == "data"
    codes = parse.load_npcwh_codes()
    assert codes and all("name" in v and "class" in v for v in codes.values())
    assert parse.load_whisk()


@pytest.mark.parametrize(("attr", "loader"), [("NPCWH_FILE", "load_npcwh_codes"), ("WHISK_TEMPLATE", "load_whisk")])
def test_missing_tracked_input_raises(monkeypatch, tmp_path, attr, loader):
    monkeypatch.setattr(parse, attr, tmp_path / "missing")
    with pytest.raises(FileNotFoundError, match="missing"):
        getattr(parse, loader)()
