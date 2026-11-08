"""Tests for the schema and read helpers in expo_catalog.db."""

from __future__ import annotations

import sqlite3

import pytest

from expo_catalog import db
from expo_catalog.db import Site


def make_site(**overrides) -> dict:
    base = dict(
        id=None,
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
        escalation="None (DED 7/10 is terminal)",
        loot_note="Shadow Serpentis commander drops",
        description="A rated deadspace complex.",
        source_url="https://wiki.eveuniversity.org/Serpentis_Phi-Outpost",
        search_text="serpentis phi-outpost combat_ded combat site low null serpentis 7/10",
    )
    base.update(overrides)
    return base


@pytest.fixture
def conn() -> sqlite3.Connection:
    connection = db.connect(":memory:")
    db.create_schema(connection)
    yield connection
    connection.close()


def seed(conn: sqlite3.Connection) -> list[int]:
    ids = [
        db.insert_site(
            conn,
            make_site(
                name="Ruined Angel Crystal Quarry",
                category="relic",
                scan_group="Relic Site",
                space="High",
                faction="Angel Cartel",
                rating=None,
                danger=1,
                danger_label="Safe",
                enemies="None",
                min_ship="T1 explo frigate (Heron/Probe/Imicus/Magnate)",
                ship_limit=None,
                ewar=None,
                escalation=None,
                search_text="ruined angel crystal quarry relic relic site high angel cartel",
            ),
        ),
        db.insert_site(conn, make_site()),
        db.insert_site(
            conn,
            make_site(
                name="Angel Hidden Hideaway",
                rating="1/10",
                danger=2,
                danger_label="Low",
                space="High",
                faction="Angel Cartel",
                search_text="angel hidden hideaway combat_ded combat site high angel cartel 1/10",
            ),
        ),
    ]
    db.insert_enemy(
        conn,
        ids[1],
        {"wave": "1", "ship_class": "frigate", "count_min": 4, "count_max": 6,
         "name": "Corelior Infantry", "tier": "T1", "ewar": "web"},
    )
    db.insert_enemy(
        conn,
        ids[1],
        {"wave": "2", "ship_class": "battleship", "count_min": 2, "count_max": 2,
         "name": "Core Admiral"},
    )
    db.set_meta(conn, "built_at", "2026-11-08T00:00:00Z")
    db.set_meta(conn, "source", "eve-university wiki")
    conn.commit()
    return ids


def test_schema_creates_expected_tables(conn):
    tables = {
        row["name"]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    assert {"sites", "site_enemies", "meta"} <= tables
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(sites)")]
    assert tuple(columns) == db.SITE_COLUMNS
    assert db.SITE_COLUMNS[0] == "id" and db.SITE_COLUMNS[-1] == "search_text"
    # idempotent
    db.create_schema(conn)


def test_load_sites_ordered_by_name(conn):
    ids = seed(conn)
    sites = db.load_sites(conn)
    assert [s.name for s in sites] == [
        "Angel Hidden Hideaway",
        "Ruined Angel Crystal Quarry",
        "Serpentis Phi-Outpost",
    ]
    assert all(isinstance(s, Site) for s in sites)
    phi = next(s for s in sites if s.name == "Serpentis Phi-Outpost")
    assert phi.id == ids[1]
    assert phi.danger == 4 and phi.danger_label == "High"
    assert phi.ewar == "web, scram, sensor damp"
    relic = sites[1]
    assert relic.faction == "Angel Cartel" and relic.rating is None and relic.ship_limit is None
    with pytest.raises(Exception):  # frozen dataclass
        phi.name = "x"  # type: ignore[misc]


def test_load_enemies(conn):
    ids = seed(conn)
    rows = db.load_enemies(conn, ids[1])
    assert [r["wave"] for r in rows] == ["1", "2"]
    assert rows[0]["ship_class"] == "frigate"
    assert (rows[0]["count_min"], rows[0]["count_max"]) == (4, 6)
    assert rows[0]["ewar"] == "web" and rows[1]["ewar"] is None
    assert db.load_enemies(conn, ids[0]) == []
    grouped = db.load_all_enemies(conn)
    assert set(grouped) == {ids[1]}
    assert len(grouped[ids[1]]) == 2


def test_enemies_cascade_on_site_delete(conn):
    ids = seed(conn)
    conn.execute("DELETE FROM sites WHERE id = ?", (ids[1],))
    assert db.load_enemies(conn, ids[1]) == []


def test_load_meta(conn):
    seed(conn)
    assert db.load_meta(conn) == {
        "built_at": "2026-11-08T00:00:00Z",
        "source": "eve-university wiki",
    }
    db.set_meta(conn, "source", "changed")
    assert db.load_meta(conn)["source"] == "changed"


def test_insert_site_accepts_site_dataclass(conn):
    site = Site.from_row(make_site(id=None))
    new_id = db.insert_site(conn, site)
    assert db.load_sites(conn)[0].id == new_id


def test_connect_file_creates_then_opens_read_only(tmp_path):
    path = tmp_path / "sub" / "catalog.sqlite"
    rw = db.connect(path)
    db.create_schema(rw)
    db.insert_site(rw, make_site())
    rw.commit()
    rw.close()
    assert path.exists()

    ro = db.connect(path)
    assert ro.row_factory is sqlite3.Row
    assert len(db.load_sites(ro)) == 1
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("DELETE FROM sites")
    ro.close()


def test_resolve_db_path_env_override(monkeypatch, tmp_path):
    monkeypatch.delenv(db.ENV_VAR, raising=False)
    assert db.resolve_db_path().name == "catalog.sqlite"
    assert db.resolve_db_path().parent.name == "data"
    monkeypatch.setenv(db.ENV_VAR, str(tmp_path / "other.sqlite"))
    assert db.resolve_db_path() == tmp_path / "other.sqlite"
    assert db.resolve_db_path(tmp_path / "explicit.sqlite") == tmp_path / "explicit.sqlite"
