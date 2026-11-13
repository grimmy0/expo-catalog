"""Headless tests for the Textual catalog app (no network, no pytest-asyncio)."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Input, Static

from expo_catalog import app as app_module
from expo_catalog import db
from expo_catalog.app import (
    CatalogApp,
    ColumnWidths,
    compute_widths,
    danger_cell,
    load_catalog,
    space_label,
    type_label,
)
from expo_catalog.db import Site

FIXTURE_SITES = [
    dict(
        name="Angel Hidden Hideaway",
        category="combat_ded",
        scan_group="Combat Site",
        is_signature=1,
        space="High",
        faction="Angel Cartel",
        rating="1/10",
        danger=2,
        danger_label="Low",
        enemies="6-9 frigates, 2 destroyers",
        min_ship="T1 destroyer",
        ship_limit="Destroyer and smaller",
        ewar="web",
        status="active",
        escalation="Angel Minor Annex",
        loot_note="Domination frigate drops",
        description="Entry-level Angel Cartel DED complex.",
        source_url="https://example.invalid/hideaway",
        search_text="angel hidden hideaway combat_ded combat site high angel cartel 1/10 active",
    ),
    dict(
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
        loot_note="Shadow Serpentis commander drops",
        description="Rated deadspace complex.",
        source_url="https://example.invalid/phi",
        search_text="serpentis phi-outpost combat_ded combat site low null serpentis 7/10 active",
    ),
    dict(
        name="Local Serpentis Mainframe",
        category="data",
        scan_group="Data Site",
        is_signature=1,
        space="High",
        faction="Serpentis",
        rating=None,
        danger=0,
        danger_label="n/a",
        enemies="None",
        min_ship="T1 explo frigate (Heron/Probe/Imicus/Magnate)",
        ship_limit=None,
        ewar=None,
        status="active",
        escalation=None,
        loot_note="Datacores, decryptors",
        description="Hack the cans.",
        source_url=None,
        search_text="local serpentis mainframe data data site high serpentis active",
    ),
    dict(
        name="Ruined Angel Crystal Quarry",
        category="relic",
        scan_group="Relic Site",
        is_signature=1,
        space="High",
        faction="Angel Cartel",
        rating=None,
        danger=1,
        danger_label="Safe",
        enemies="None",
        min_ship="T1 explo frigate (Heron/Probe/Imicus/Magnate)",
        ship_limit=None,
        ewar=None,
        status="active",
        escalation=None,
        loot_note="Salvage materials",
        description=None,
        source_url=None,
        search_text="ruined angel crystal quarry relic relic site high angel cartel active",
    ),
    dict(
        name="Forgotten Perimeter Gateway",
        category="wormhole_relic",
        scan_group="Relic Site",
        is_signature=1,
        space="C1-C3",
        faction="Sleepers",
        rating="C1-C3",
        danger=3,
        danger_label="Medium",
        enemies="2 waves of sleeper frigates and cruisers",
        min_ship="T3 cruiser or Stratios",
        ship_limit=None,
        ewar="neut, scram",
        status="active",
        escalation=None,
        loot_note="Ancient salvage",
        description="Sleeper relic site.",
        source_url=None,
        search_text="forgotten perimeter gateway wormhole_relic relic site c1-c3 sleepers active",
    ),
    # The last two are hidden by default (status removed / unverified).
    dict(
        name="Serpentis Narcotic Warehouses",
        category="combat_unrated",
        scan_group="Combat Site",
        is_signature=1,
        space="Low, Null",
        faction="Serpentis",
        rating="Unrated",
        danger=3,
        danger_label="Medium",
        enemies="8-12 frigates, 4 cruisers, 2 battlecruisers",
        min_ship="Battlecruiser",
        ship_limit=None,
        ewar="web, scram",
        status="removed",
        escalation=None,
        loot_note=None,
        description="Unrated complex no longer in the game.",
        source_url=None,
        search_text="serpentis narcotic warehouses combat_unrated combat site low null serpentis unrated removed",
    ),
    dict(
        name="Amarr Battlefield",
        category="fw_complex",
        scan_group="Beacon",
        is_signature=0,
        space="Low (FW warzone)",
        faction=None,
        rating="Battlefield plex",
        danger=2,
        danger_label="Low",
        enemies="1 frigate",
        min_ship="T1 frigate",
        ship_limit="Frigate only",
        ewar=None,
        status="unverified",
        escalation=None,
        loot_note=None,
        description=None,
        source_url=None,
        search_text="amarr battlefield fw_complex beacon low (fw warzone) battlefield plex unverified",
    ),
]

FIXTURE_ENEMIES = {
    "Forgotten Perimeter Gateway": [
        {
            "wave": "1",
            "ship_class": "frigate",
            "count_min": 2,
            "count_max": 3,
            "name": "Emergent Patroller",
            "tier": None,
            "ewar": None,
        },
        {
            "wave": "2",
            "ship_class": "cruiser",
            "count_min": 1,
            "count_max": 1,
            "name": "Sleepless Guardian",
            "tier": None,
            "ewar": "neut, scram",
        },
    ],
    "Angel Hidden Hideaway": [
        {
            "wave": None,
            "ship_class": "frigate",
            "count_min": 6,
            "count_max": 9,
            "name": "Gistii Hunter",
            "tier": "T1",
            "ewar": "web",
        },
    ],
}

ALL_NAMES_SORTED = sorted(s["name"] for s in FIXTURE_SITES)
HIDDEN_NAMES = sorted(s["name"] for s in FIXTURE_SITES if s["status"] in app_module.HIDDEN_STATUSES)
NAMES_SORTED = sorted(set(ALL_NAMES_SORTED) - set(HIDDEN_NAMES))
"""Rows listed by default (removed / unverified sites are hidden)."""


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "catalog.sqlite"
    conn = db.connect(path)
    db.create_schema(conn)
    for spec in FIXTURE_SITES:
        site_id = db.insert_site(conn, spec)
        for enemy in FIXTURE_ENEMIES.get(spec["name"], []):
            db.insert_enemy(conn, site_id, enemy)
    db.set_meta(conn, "built_at", "2026-11-08")
    conn.commit()
    conn.close()
    return path


def run_async(coro):
    return asyncio.run(coro)


def table_names(table: DataTable) -> list[str]:
    return [table.get_row_at(i)[0].plain for i in range(table.row_count)]


def table_column(table: DataTable, index: int) -> list[str]:
    return [table.get_row_at(i)[index].plain for i in range(table.row_count)]


def make_site(**overrides) -> Site:
    base = dict(FIXTURE_SITES[1], id=1)
    base.update(overrides)
    return Site(**base)


def detail_text(app: CatalogApp) -> str:
    content = app.query_one("#detail", Static).content
    return content.plain if hasattr(content, "plain") else str(content)


def test_danger_cell_rendering():
    assert danger_cell(3, "Medium").plain == "▮▮▮▯▯ Medium"
    assert danger_cell(5, "Deadly").plain == "▮▮▮▮▮ Deadly"
    assert danger_cell(1, "Safe").plain == "▮▯▯▯▯ Safe"
    assert danger_cell(0, "n/a").plain == "n/a"


def test_rows_render_sorted_with_status_and_detail(db_path):
    async def main():
        app = CatalogApp(load_catalog(db_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#table", DataTable)
            assert [str(c.label) for c in table.ordered_columns] == [
                "Name",
                "Type",
                "Space",
                "Danger",
                "Enemies",
                "Min ship",
            ]
            # Type and Space have fixed widths, the rest size to content
            by_key = {str(c.key.value): c for c in table.ordered_columns}
            assert (by_key["type"].width, by_key["type"].auto_width) == (12, False)
            assert (by_key["space"].width, by_key["space"].auto_width) == (14, False)
            assert by_key["name"].auto_width is True
            assert table.row_count == 5
            assert len(HIDDEN_NAMES) == 2
            assert table_names(table) == NAMES_SORTED
            assert table.cursor_row == 0
            # Type column derived from category + rating
            assert dict(zip(table_names(table), table_column(table, 1), strict=True)) == {
                "Angel Hidden Hideaway": "DED 1/10",
                "Forgotten Perimeter Gateway": "WH relic",
                "Local Serpentis Mainframe": "Data",
                "Ruined Angel Crystal Quarry": "Relic",
                "Serpentis Phi-Outpost": "DED 7/10",
            }
            # Space column: as-is, dim
            phi = NAMES_SORTED.index("Serpentis Phi-Outpost")
            assert table.get_row_at(phi)[2].plain == "Low, Null"
            assert table.get_row_at(phi)[1].style == "dim"
            assert table.get_row_at(phi)[2].style == "dim"
            # danger cell for the first row (Angel Hidden Hideaway, danger 2)
            assert table.get_row_at(0)[3].plain == "▮▮▯▯▯ Low"
            # n/a row for the data site
            idx = NAMES_SORTED.index("Local Serpentis Mainframe")
            assert table.get_row_at(idx)[3].plain == "n/a"
            assert app.query_one("#status", Static).content == "5 / 7 sites · 2 hidden (ctrl+r)"
            assert isinstance(app.focused, Input)
            text = detail_text(app)
            assert "Angel Hidden Hideaway" in text
            assert "Angel Minor Annex" in text  # escalation
            assert "Gistii Hunter" in text  # enemy row
            assert "https://example.invalid/hideaway" in text

    run_async(main())


def test_typing_filters_rows_live(db_path):
    async def main():
        app = CatalogApp(load_catalog(db_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#table", DataTable)
            await pilot.press("s", "e", "r", "p")
            await pilot.pause()
            assert app.query_one("#filter", Input).value == "serp"
            # prefix match ranks first, then the mid-text match
            assert table_names(table) == ["Serpentis Phi-Outpost", "Local Serpentis Mainframe"]
            assert table.cursor_row == 0
            # the removed "Serpentis Narcotic Warehouses" matches too but stays hidden
            assert app.query_one("#status", Static).content == "2 / 7 sites · 1 hidden (ctrl+r)"
            assert "Serpentis Phi-Outpost" in detail_text(app)

            # fzf operators: AND + exclude + exact
            await pilot.press("space", "!", "d", "a", "t", "a")
            await pilot.pause()
            assert table_names(table) == ["Serpentis Phi-Outpost"]
            assert app.query_one("#status", Static).content == "1 / 7 sites · 1 hidden (ctrl+r)"
            await pilot.press("space", "'", "z", "z")
            await pilot.pause()
            assert table.row_count == 0
            # nothing hidden matches either, so no hidden count
            assert app.query_one("#status", Static).content == "0 / 7 sites"
            assert "No sites match" in detail_text(app)
            # input keeps focus throughout
            assert isinstance(app.focused, Input)

    run_async(main())


def test_down_arrow_moves_cursor_and_updates_detail(db_path):
    async def main():
        app = CatalogApp(load_catalog(db_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#table", DataTable)
            assert "Angel Hidden Hideaway" in detail_text(app)
            await pilot.press("down")
            await pilot.pause()
            assert table.cursor_row == 1
            text = detail_text(app)
            assert "Forgotten Perimeter Gateway" in text
            assert "Sleepless Guardian" in text
            assert "neut, scram" in text
            assert isinstance(app.focused, Input)  # focus stayed on the filter

            await pilot.press("ctrl+j")
            await pilot.pause()
            assert table.cursor_row == 2
            assert "Local Serpentis Mainframe" in detail_text(app)
            await pilot.press("ctrl+k", "up")
            await pilot.pause()
            assert table.cursor_row == 0

    run_async(main())


def test_escape_clears_query_then_quits(db_path):
    async def main():
        app = CatalogApp(load_catalog(db_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#table", DataTable)
            filter_input = app.query_one("#filter", Input)
            await pilot.press("a", "n", "g", "e", "l")
            await pilot.pause()
            assert table.row_count == 2
            await pilot.press("escape")
            await pilot.pause()
            assert filter_input.value == ""
            assert table.row_count == 5
            assert isinstance(app.focused, Input)
            assert app.return_code is None
            await pilot.press("escape")
            await pilot.pause()
        assert app.return_code == 0

    run_async(main())


def test_enter_toggles_detail_panel(db_path):
    async def main():
        app = CatalogApp(load_catalog(db_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            pane = app.query_one("#detail-pane", VerticalScroll)
            assert pane.display is True
            await pilot.press("enter")
            await pilot.pause()
            assert pane.display is False
            await pilot.press("enter")
            await pilot.pause()
            assert pane.display is True

    run_async(main())


async def type_text(pilot, text: str) -> None:
    """Type ``text`` into the focused Input one character at a time."""
    await pilot.press(*text)
    await pilot.pause()


def test_hidden_statuses_toggle_with_ctrl_r(db_path):
    async def main():
        app = CatalogApp(load_catalog(db_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#table", DataTable)
            status = app.query_one("#status", Static)
            assert app.show_hidden is False
            assert table_names(table) == NAMES_SORTED
            assert status.content == "5 / 7 sites · 2 hidden (ctrl+r)"

            await pilot.press("ctrl+r")
            await pilot.pause()
            assert app.show_hidden is True
            assert table_names(table) == ALL_NAMES_SORTED
            assert status.content == "7 / 7 sites"
            assert isinstance(app.focused, Input)  # works while the filter has focus
            # the detail panel shows the first row again
            assert ALL_NAMES_SORTED[0] in detail_text(app)

            # the toggle combines with the filter (both prefix matches tie, so they keep name order)
            await type_text(pilot, "serp")
            assert table_names(table) == [
                "Serpentis Narcotic Warehouses",
                "Serpentis Phi-Outpost",
                "Local Serpentis Mainframe",
            ]
            assert status.content == "3 / 7 sites"

            await pilot.press("ctrl+r")
            await pilot.pause()
            assert app.show_hidden is False
            assert table_names(table) == ["Serpentis Phi-Outpost", "Local Serpentis Mainframe"]
            assert status.content == "2 / 7 sites · 1 hidden (ctrl+r)"
            assert app.query_one("#filter", Input).value == "serp"

    run_async(main())


def test_status_term_shows_hidden_sites_without_the_toggle(db_path):
    async def main():
        app = CatalogApp(load_catalog(db_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#table", DataTable)
            status = app.query_one("#status", Static)
            await type_text(pilot, "status:removed")
            assert app.query_one("#filter", Input).value == "status:removed"
            assert app.show_hidden is False
            assert table_names(table) == ["Serpentis Narcotic Warehouses"]
            assert status.content == "1 / 7 sites"
            assert "Serpentis Narcotic Warehouses" in detail_text(app)

            # any status: term (even negated) suspends the default hiding
            await pilot.press("escape")
            await type_text(pilot, "!status:removed")
            assert table_names(table) == sorted(set(ALL_NAMES_SORTED) - {"Serpentis Narcotic Warehouses"})
            assert status.content == "6 / 7 sites"

            # an unknown field name falls through to the fuzzy matcher (no match here)
            await pilot.press("escape")
            await type_text(pilot, "foo:removed")
            assert table.row_count == 0
            assert status.content == "0 / 7 sites"

    run_async(main())


def test_field_terms_filter_and_plain_terms_rank(db_path):
    async def main():
        app = CatalogApp(load_catalog(db_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#table", DataTable)
            status = app.query_one("#status", Static)

            await type_text(pilot, "type:relic")
            assert table_names(table) == ["Forgotten Perimeter Gateway", "Ruined Angel Crystal Quarry"]
            assert status.content == "2 / 7 sites"
            await type_text(pilot, " angel")
            assert table_names(table) == ["Ruined Angel Crystal Quarry"]

            # the plain part keeps fzf ranking: prefix match first, scattered match last
            await pilot.press("escape")
            await type_text(pilot, "space:high ang")
            assert table_names(table) == [
                "Angel Hidden Hideaway",
                "Ruined Angel Crystal Quarry",
                "Local Serpentis Mainframe",
            ]
            assert status.content == "3 / 7 sites"

            # numeric field with the default hiding still applied
            await pilot.press("escape")
            await type_text(pilot, "danger:<=2 !space:null")
            assert table_names(table) == [
                "Angel Hidden Hideaway",
                "Local Serpentis Mainframe",
                "Ruined Angel Crystal Quarry",
            ]
            assert status.content == "3 / 7 sites · 1 hidden (ctrl+r)"  # Amarr Battlefield (danger 2)
            await pilot.press("ctrl+r")
            await pilot.pause()
            assert "Amarr Battlefield" in table_names(table)
            assert status.content == "4 / 7 sites"

    run_async(main())


def test_show_hidden_flag_starts_with_everything_listed(db_path):
    async def main():
        app = CatalogApp(load_catalog(db_path), show_hidden=True)
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#table", DataTable)
            assert table_names(table) == ALL_NAMES_SORTED
            assert app.query_one("#status", Static).content == "7 / 7 sites"
            await pilot.press("ctrl+r")
            await pilot.pause()
            assert table_names(table) == NAMES_SORTED

    run_async(main())


def test_run_with_missing_db_exits_with_hint(tmp_path, capsys):
    missing = tmp_path / "nope.sqlite"
    with pytest.raises(SystemExit) as excinfo:
        app_module.run(str(missing))
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert f"Database not found at {missing}" in err
    assert "uv run python -m scraper.build" in err


# -- Type / Space labels ------------------------------------------------------


@pytest.mark.parametrize(
    ("category", "rating", "expected"),
    [
        ("combat_ded", "3/10", "DED 3/10"),
        ("combat_ded", "10/10", "DED 10/10"),
        ("combat_ded", None, "DED"),
        ("combat_unrated", "Unrated", "Unrated"),
        ("combat_anomaly", "Tier 4", "Anom T4"),
        ("combat_anomaly", "tier 10", "Anom T10"),
        ("combat_anomaly", None, "Anomaly"),
        ("data", "Scan difficulty III", "Data"),
        ("relic", None, "Relic"),
        ("gas", None, "Gas"),
        ("chemical_lab", "Unrated", "Chem lab"),
        ("ghost", "Ghost site", "Ghost"),
        ("sleeper_cache", None, "Sleeper"),
        ("wormhole_combat", "C5", "WH combat"),
        ("wormhole_data", "C3", "WH data"),
        ("wormhole_relic", "C1", "WH relic"),
        ("wormhole_gas", "C1-C4", "WH gas"),
        ("wormhole_ore", "C5-C6", "WH ore"),
        ("ore", None, "Ore"),
        ("ice", None, "Ice"),
        ("fw_complex", "Small plex", "FW plex"),
        ("insurgency", None, "Insurgency"),
        ("homefront", "Homefront (5 pilots)", "Homefront"),
        ("pochven", None, "Pochven"),
        ("drifter", None, "Drifter"),
        ("incursion", "Vanguard", "Incursion"),
        ("cosmos", "COSMOS L4", "COSMOS"),
        ("event", "Crimson Harvest (2023-2026)", "Event"),
        ("wormhole_connection", "→ C5", "Wormhole"),
        ("other", None, "Other"),
        ("brand_new_category_xyz", None, "Brand new c…"),
    ],
)
def test_type_label(category, rating, expected):
    label = type_label(make_site(category=category, rating=rating))
    assert label == expected
    assert len(label) <= 12


def test_space_label_truncates_to_14_with_ellipsis():
    assert space_label("High") == "High"
    assert space_label("Low, Null") == "Low, Null"
    # compacts separators before clipping
    assert space_label("High, Low, Null") == "High/Low/Null"
    long = "Drifter wormhole J110145 (Liberated Barbican, Cataclysmic Variable)"
    assert space_label(long) == "Drifter wormh…"
    assert len(space_label(long)) == 14
    assert space_label("Incursion constellation (High, Low, Null)", width=20) == "Incursion constella…"


def test_compute_widths_fits_terminal_and_keeps_name_wide():
    fixed = 12 + 14 + 12 + 2 * 6 + 4  # Type, Space, Danger, cell padding, margins + scrollbar
    for cols in (120, 160, 200):
        widths = compute_widths(cols)
        assert widths.name >= 34
        assert widths.name + widths.enemies + widths.min_ship + fixed <= cols
    assert compute_widths(120) == ColumnWidths(name=34, enemies=18, min_ship=14)
    assert compute_widths(160) == ColumnWidths(name=45, enemies=34, min_ship=27)
    assert compute_widths(200).name == 49  # never wider than the longest site name
    assert compute_widths(80).name == 34  # narrow terminals scroll instead of squeezing Name


def test_space_column_truncated_in_table_but_full_in_detail(db_path):
    long_space = "Drifter wormhole J110145 (Liberated Barbican, Cataclysmic Variable)"
    conn = db.connect(db_path, readonly=False)
    conn.execute("UPDATE sites SET space = ? WHERE name = 'Angel Hidden Hideaway'", (long_space,))
    conn.commit()
    conn.close()

    async def main():
        app = CatalogApp(load_catalog(db_path))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            table = app.query_one("#table", DataTable)
            assert table.get_row_at(0)[2].plain == "Drifter wormh…"
            assert long_space in detail_text(app)
            assert app._widths == compute_widths(160)

    run_async(main())


# -- command line ---------------------------------------------------------------


def test_cli_db_flag_is_passed_to_run(monkeypatch, tmp_path):
    seen: list[object] = []
    monkeypatch.setattr(app_module, "run", lambda db_path=None, *, show_hidden=False: seen.append(db_path))
    app_module.main(["--db", str(tmp_path / "x.sqlite")])
    assert seen == [str(tmp_path / "x.sqlite")]
    app_module.main([])
    assert seen[-1] is None


def test_cli_all_flag_starts_with_hidden_sites_shown(monkeypatch):
    assert app_module.build_parser().parse_args(["--all"]).all is True
    assert app_module.build_parser().parse_args([]).all is False
    seen: list[tuple[object, bool]] = []
    monkeypatch.setattr(
        app_module,
        "run",
        lambda db_path=None, *, show_hidden=False: seen.append((db_path, show_hidden)),
    )
    app_module.main(["--all"])
    app_module.main(["--all", "--db", "x.sqlite"])
    app_module.main([])
    assert seen == [(None, True), ("x.sqlite", True), (None, False)]


def test_run_passes_show_hidden_to_the_app(monkeypatch, db_path):
    created: list[tuple[object, bool]] = []

    class FakeApp:
        def __init__(self, catalog, *, show_hidden=False):
            created.append((catalog, show_hidden))

        def run(self):
            pass

    monkeypatch.setattr(app_module, "CatalogApp", FakeApp)
    app_module.run(db_path, show_hidden=True)
    app_module.run(db_path)
    assert [flag for _catalog, flag in created] == [True, False]
    assert len(created[0][0].sites) == 7


def test_cli_refresh_runs_scraper_then_launches(monkeypatch, tmp_path):
    (tmp_path / "scraper").mkdir()
    (tmp_path / "scraper" / "__init__.py").write_text("")
    monkeypatch.setattr(app_module.db, "REPO_ROOT", tmp_path)
    calls: list[tuple[list[str], object]] = []

    def fake_run(cmd, cwd=None, **kwargs):
        calls.append((cmd, cwd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(app_module.subprocess, "run", fake_run)
    launched: list[object] = []
    monkeypatch.setattr(app_module, "run", lambda db_path=None, *, show_hidden=False: launched.append(db_path))

    app_module.main(["--refresh", "--db", "custom.sqlite"])
    assert calls == [([sys.executable, "-m", "scraper", "refresh"], tmp_path)]
    assert launched == ["custom.sqlite"]


def test_cli_refresh_reports_scraper_failure(monkeypatch, tmp_path, capsys):
    (tmp_path / "scraper").mkdir()
    (tmp_path / "scraper" / "__init__.py").write_text("")
    monkeypatch.setattr(app_module.db, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(app_module.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 3))
    monkeypatch.setattr(app_module, "run", lambda db_path=None, **kwargs: pytest.fail("TUI must not launch"))
    with pytest.raises(SystemExit) as excinfo:
        app_module.main(["--refresh"])
    assert excinfo.value.code == 1
    assert "exited with code 3" in capsys.readouterr().err


def test_cli_refresh_without_scraper_package_exits_2(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(app_module.db, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(app_module.subprocess, "run", lambda *a, **kw: pytest.fail("subprocess must not run"))
    with pytest.raises(SystemExit) as excinfo:
        app_module.main(["--refresh"])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert "no scraper/ package" in err and str(tmp_path) in err


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        app_module.main(["--version"])
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.startswith("expo-catalog ")
