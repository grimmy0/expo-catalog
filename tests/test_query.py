"""Tests for the field-term parser and matchers in expo_catalog.query."""

from __future__ import annotations

import subprocess
import sys

import pytest

from expo_catalog.db import Site
from expo_catalog.query import FieldFilter, Query, parse_query, space_tokens


def make_site(**overrides) -> Site:
    base = dict(
        id=1,
        name="Serpentis Phi-Outpost",
        category="combat_ded",
        scan_group="Combat Site",
        is_signature=1,
        space="Low, Null",
        faction="Serpentis",
        rating="7/10",
        danger=4,
        danger_label="High",
        enemies="10-14 frigates, 6 cruisers, 4 battleships",
        min_ship="Battleship or T3 cruiser",
        ship_limit="Battleship and smaller",
        ewar="web, scram, sensor damp",
        status="active",
        escalation=None,
        loot_note=None,
        description=None,
        source_url=None,
        search_text="serpentis phi-outpost combat_ded combat site low null serpentis 7/10 active",
    )
    base.update(overrides)
    return Site(**base)


def matches(text: str, **overrides) -> bool:
    return parse_query(text).matches(make_site(**overrides))


def test_query_module_does_not_import_the_tui():
    """query.py must stay importable without Textual or expo_catalog.app (no import cycle)."""
    code = (
        "import sys, expo_catalog.query\n"
        "print('textual' in sys.modules, 'rich' in sys.modules, 'expo_catalog.app' in sys.modules)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.split() == ["False", "False", "False"]


# -- space_tokens ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("space", "expected"),
    [
        ("High", {"high"}),
        ("High, Low, Null", {"high", "low", "null"}),
        ("Low/Null (Null-sec)", {"low", "null"}),
        ("Low (FW warzone)", {"low"}),
        ("Null (Drone regions)", {"null"}),
        ("K-space (High, Low, Null)", {"high", "low", "null"}),
        ("K-space (Jove Observatory systems)", {"high", "low", "null"}),
        ("C3", {"c3"}),
        ("C1-C4", {"c1", "c2", "c3", "c4"}),
        ("C5-C6", {"c5", "c6"}),
        ("C1-C6", {"c1", "c2", "c3", "c4", "c5", "c6"}),
        ("Wormhole C2-C6", {"wormhole", "c2", "c3", "c4", "c5", "c6"}),
        ("Wormhole", {"wormhole"}),
        ("Null, Wormhole", {"null", "wormhole"}),
        ("Shattered wormholes", {"shattered", "wormhole"}),
        ("Shattered, Thera", {"shattered", "thera"}),
        ("Thera", {"thera"}),
        ("Pochven (border systems)", {"pochven"}),
        ("Drifter wormhole J174618 (Azdaja Redoubt, Wolf-Rayet)", {"drifter", "wormhole"}),
        ("Any (small-ship wormhole)", {"*", "wormhole"}),
        ("Various", {"*"}),
        ("Unknown", {"*"}),
        ("EDENCOM minor-victory systems", set()),
        ("", set()),
    ],
)
def test_space_tokens(space, expected):
    tokens = space_tokens(space)
    assert isinstance(tokens, frozenset)
    assert tokens == expected


def test_space_tokens_ignores_classes_that_do_not_exist():
    assert space_tokens("C1-C13") == {"c1", "c2", "c3", "c4", "c5", "c6", "c13"}
    assert space_tokens("C7") == set()
    assert space_tokens("J110145") == set()  # a system name is not a class


# -- parsing --------------------------------------------------------------------


def test_plain_terms_pass_through_unchanged():
    query = parse_query("serp 'den !relic ^angel site$")
    assert query == Query("serp 'den !relic ^angel site$", ())
    assert parse_query("") == Query("", ())
    assert parse_query("   ") == Query("", ())


def test_field_terms_are_split_from_plain_terms():
    query = parse_query("space:c3  forgotten type:relic !data danger:<=3")
    assert query.plain == "forgotten !data"
    assert query.filters == (
        FieldFilter("space", "c3"),
        FieldFilter("type", "relic"),
        FieldFilter("danger", "<=3"),
    )


def test_unknown_field_name_is_a_plain_term():
    assert parse_query("foo:bar") == Query("foo:bar", ())
    assert parse_query("https://wiki serp") == Query("https://wiki serp", ())
    assert parse_query("!foo:bar") == Query("!foo:bar", ())


def test_field_name_and_value_are_case_insensitive():
    assert parse_query("SPACE:C3 Type:DED").filters == (FieldFilter("space", "c3"), FieldFilter("type", "ded"))


def test_negated_field_term():
    assert parse_query("!space:c3").filters == (FieldFilter("space", "c3", negate=True),)
    assert matches("!space:c3", space="High")
    assert not matches("!space:c3", space="C3")
    assert matches("!faction:angel", faction=None)  # NULL never matches, so its negation always does


def test_field_term_without_a_value_is_dropped():
    assert parse_query("space:") == Query("", ())
    assert parse_query("!status: serp") == Query("serp", ())
    assert parse_query("danger:").matches(make_site())


def test_has_field():
    query = parse_query("space:c3 !status:removed serp")
    assert query.has_field("space")
    assert query.has_field("status")  # negated terms count too
    assert not query.has_field("type")
    assert not parse_query("status").has_field("status")  # a plain term is not a field
    assert not Query("serp").has_field("status")


def test_query_without_filters_matches_everything():
    assert parse_query("serp !data").matches(make_site())
    assert Query("").matches(make_site(space="Unknown", faction=None, ewar=None))


def test_filters_are_anded():
    assert matches("space:null danger:>=4 faction:serp")
    assert not matches("space:null danger:>=4 faction:angel")
    assert not matches("space:high danger:>=4 faction:serp")


# -- space: ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("space", "term", "expected"),
    [
        # raw substring
        ("Null (Delve)", "delve", True),
        ("Low (FW warzone)", "fw", True),
        ("Pochven (border systems)", "border", True),
        ("High (0.5-0.8)", "0.5", True),
        # tokens and aliases
        ("High, Low", "high", True),
        ("High, Low", "null", False),
        ("Low/Null (Derelik)", "null", True),
        ("High", "hs", True),
        ("Low", "ls", True),
        ("Null", "ns", True),
        ("High", "ls", False),
        ("K-space (Jove Observatory systems)", "null", True),
        ("High", "k-space", True),
        ("C3", "k-space", False),
        ("Pochven", "pochven", True),
        ("Low, Pochven", "ls", True),
        # classes, ranges and the generic wormhole
        ("C3", "c3", True),
        ("C3", "c4", False),
        ("C1-C4", "c2", True),
        ("C1-C4", "c5", False),
        ("C5-C6", "c6", True),
        ("Wormhole C2-C6", "c3", True),
        ("Wormhole C2-C6", "c1", False),
        ("Wormhole", "c1", True),
        ("Wormhole", "c6", True),
        ("Wormhole", "c13", True),
        ("Wormhole", "thera", True),
        ("Wormhole", "shattered", True),
        ("Wormhole", "pochven", False),
        ("Null, Wormhole", "c3", True),
        ("Null, Wormhole", "null", True),
        ("Thera", "thera", True),
        ("Shattered, Thera", "shattered", True),
        ("Thera", "c3", False),
        ("Drifter wormhole J174618 (Azdaja Redoubt, Wolf-Rayet)", "drifter", True),
        ("Drifter wormhole J174618 (Azdaja Redoubt, Wolf-Rayet)", "c3", False),
        # space:wormhole and its aliases cover every classed site
        ("C3", "wormhole", True),
        ("C5-C6", "wh", True),
        ("Thera", "j-space", True),
        ("Shattered", "wormhole", True),
        ("Wormhole", "wh", True),
        ("Drifter wormholes", "wormhole", True),
        ("Null, Wormhole", "wormhole", True),
        ("High, Low, Null", "wormhole", False),
        ("High", "c3", False),
        # wildcard spaces match anything
        ("Any (small-ship wormhole)", "c3", True),
        ("Various", "pochven", True),
        ("Unknown", "delve", True),
    ],
)
def test_space_field(space, term, expected):
    assert matches(f"space:{term}", space=space) is expected
    assert matches(f"SPACE:{term.upper()}", space=space) is expected


# -- type: ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "term", "expected"),
    [
        # Type column label
        (dict(category="combat_ded", rating="3/10"), "ded", True),
        (dict(category="combat_ded", rating="3/10"), "ded 3/10", True),
        (dict(category="combat_ded", rating="3/10"), "3/10", True),
        (dict(category="combat_ded", rating="3/10"), "relic", False),
        (dict(category="combat_anomaly", rating="Tier 4", scan_group="Combat Anomaly"), "anom", True),
        (dict(category="combat_anomaly", rating="Tier 4", scan_group="Combat Anomaly"), "t4", True),
        (dict(category="wormhole_relic", rating="C3", scan_group="Relic Site"), "wh", True),
        (dict(category="wormhole_relic", rating="C3", scan_group="Relic Site"), "wh relic", True),
        (dict(category="fw_complex", rating="Small plex", scan_group="Beacon"), "fw", True),
        (dict(category="chemical_lab", rating=None, scan_group="Gas Site"), "chem", True),
        (dict(category="sleeper_cache", rating=None, scan_group="Data Site"), "sleeper", True),
        (dict(category="wormhole_connection", rating="→ C5", scan_group="Wormhole"), "wormhole", True),
        # category with underscores replaced
        (dict(category="wormhole_relic", rating="C3", scan_group="Relic Site"), "wormhole relic", True),
        (dict(category="wormhole_relic", rating="C3", scan_group="Relic Site"), "relic", True),
        (dict(category="combat_ded", rating="3/10"), "combat ded", True),
        (dict(category="combat_unrated", rating="Unrated"), "combat", True),
        (dict(category="combat_unrated", rating="Unrated"), "combat_unrated", False),
        # scan group
        (dict(category="relic", rating=None, scan_group="Relic Site"), "relic site", True),
        (dict(category="ghost", rating="Ghost site", scan_group="Data Site"), "data", True),
        (dict(category="ore", rating=None, scan_group="Ore Anomaly"), "anom", True),
        # rating
        (dict(category="event", rating="Crimson Harvest (2025)", scan_group="Combat Site"), "crimson", True),
        (dict(category="event", rating=None, scan_group="Combat Site"), "crimson", False),
    ],
)
def test_type_field(overrides, term, expected):
    assert matches(f"type:{term}", **overrides) is expected


# -- danger: --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("term", "matching_levels"),
    [
        ("3", {3}),
        ("=3", {3}),
        ("<=3", {0, 1, 2, 3}),
        (">=4", {4, 5}),
        ("<3", {0, 1, 2}),
        (">2", {3, 4, 5}),
        ("2-4", {2, 3, 4}),
        ("0", {0}),
        ("9", set()),
        ("<=9", {0, 1, 2, 3, 4, 5}),
        # labels stand in for numbers (case-insensitive)
        ("high", {4}),
        ("Deadly", {5}),
        ("n/a", {0}),
        ("<=medium", {0, 1, 2, 3}),
        (">low", {3, 4, 5}),
        ("safe-medium", {1, 2, 3}),
        ("2-high", {2, 3, 4}),
        ("medium-2", set()),  # empty range
        # invalid values match nothing
        ("foo", set()),
        ("<", set()),
        ("<=", set()),
        ("3-", set()),
        ("-1", set()),
        ("1-2-3", set()),
        ("<=2-4", set()),
        ("3.5", set()),
        ("==3", set()),
    ],
)
def test_danger_field(term, matching_levels):
    levels = {level for level in range(6) if matches(f"danger:{term}", danger=level)}
    assert levels == matching_levels


def test_danger_negation_and_label_case():
    assert matches("!danger:>=4", danger=3)
    assert not matches("!danger:>=4", danger=5)
    assert matches("danger:MEDIUM", danger=3)
    assert matches("DANGER:<=Medium", danger=1)


# -- substring fields -----------------------------------------------------------


def test_ship_status_faction_name_ewar_substrings():
    assert matches("ship:battleship")
    assert matches("ship:T3")
    assert not matches("ship:frigate")
    assert matches("status:act")
    assert matches("status:removed", status="removed")
    assert not matches("status:removed")
    assert matches("faction:serp")
    assert matches("faction:SERPENTIS")
    assert not matches("faction:angel")
    assert matches("name:phi")
    assert matches("name:phi-out")
    assert not matches("name:angel")
    assert matches("ewar:scram")
    assert matches("ewar:sensor")
    assert not matches("ewar:neut")


def test_null_columns_never_match():
    assert not matches("faction:serp", faction=None)
    assert not matches("faction:none", faction=None)
    assert not matches("ewar:web", ewar=None)
    assert not matches("ewar:none", ewar=None)
