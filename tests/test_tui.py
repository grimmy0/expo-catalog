"""Headless tests for the Textual catalog app (no network, no pytest-asyncio)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Input, Static

from expo_catalog import app as app_module
from expo_catalog import db
from expo_catalog.app import CatalogApp, danger_cell, load_catalog

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

NAMES_SORTED = sorted(s["name"] for s in FIXTURE_SITES)


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
    return [table.get_row_at(i)[0] for i in range(table.row_count)]


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
                "Danger",
                "Enemies",
                "Min ship",
            ]
            assert table.row_count == 5
            assert table_names(table) == NAMES_SORTED
            assert table.cursor_row == 0
            # danger cell for the first row (Angel Hidden Hideaway, danger 2)
            assert table.get_row_at(0)[1].plain == "▮▮▯▯▯ Low"
            # n/a row for the data site
            idx = NAMES_SORTED.index("Local Serpentis Mainframe")
            assert table.get_row_at(idx)[1].plain == "n/a"
            assert app.query_one("#status", Static).content == "5 / 5 sites"
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
            assert app.query_one("#status", Static).content == "2 / 5 sites"
            assert "Serpentis Phi-Outpost" in detail_text(app)

            # fzf operators: AND + exclude + exact
            await pilot.press("space", "!", "d", "a", "t", "a")
            await pilot.pause()
            assert table_names(table) == ["Serpentis Phi-Outpost"]
            await pilot.press("space", "'", "z", "z")
            await pilot.pause()
            assert table.row_count == 0
            assert app.query_one("#status", Static).content == "0 / 5 sites"
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


def test_run_with_missing_db_exits_with_hint(tmp_path, capsys):
    missing = tmp_path / "nope.sqlite"
    with pytest.raises(SystemExit) as excinfo:
        app_module.run(str(missing))
    assert excinfo.value.code == 1
    err = capsys.readouterr().err
    assert f"Database not found at {missing}" in err
    assert "uv run python -m scraper.build" in err
