"""SQLite schema and read helpers for the exploration catalog.

This module is the single source of truth for the database layout. The DB
builder (``scraper.build``) imports :data:`SCHEMA` / :func:`create_schema` and
the small insert helpers; the TUI only ever reads through :func:`load_sites`,
:func:`load_enemies` and :func:`load_meta`.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass, fields
from pathlib import Path

__all__ = [
    "CATEGORIES",
    "DANGER_LABELS",
    "DEFAULT_DB_PATH",
    "ENEMY_COLUMNS",
    "ENV_VAR",
    "SCAN_GROUPS",
    "SCHEMA",
    "SITE_COLUMNS",
    "STATUSES",
    "Site",
    "connect",
    "create_schema",
    "insert_enemy",
    "insert_site",
    "load_all_enemies",
    "load_enemies",
    "load_meta",
    "load_sites",
    "resolve_db_path",
    "set_meta",
]

ENV_VAR = "EXPO_CATALOG_DB"
"""Environment variable that overrides the default database location."""

_PROJECT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "catalog.sqlite"

DEFAULT_DB_PATH: Path = Path(os.environ.get(ENV_VAR) or _PROJECT_DB_PATH)
"""``<project>/data/catalog.sqlite`` unless ``EXPO_CATALOG_DB`` is set."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,            -- exact in-game site name
  category TEXT NOT NULL,        -- one of CATEGORIES (combat_ded, data, wormhole_relic, ore, event, ...)
  scan_group TEXT NOT NULL,      -- probe-scanner group, one of SCAN_GROUPS (Combat Site, Data Site, ... Beacon)
  is_signature INTEGER NOT NULL, -- 1 = must be probed down, 0 = anomaly/beacon
  space TEXT NOT NULL,           -- e.g. "High", "Low, Null", "C1-C4", "Pochven", "Thera", "Any"
  faction TEXT,                  -- NPC faction or NULL
  rating TEXT,                   -- "3/10", "Unrated", "Class 4", "C3" ... or NULL
  danger INTEGER NOT NULL,       -- 0..5
  danger_label TEXT NOT NULL,    -- n/a | Safe | Low | Medium | High | Deadly
  enemies TEXT NOT NULL,         -- human summary, e.g. "4-7 frigates, 2 cruisers, 1 battleship" or "None"
  min_ship TEXT NOT NULL,        -- minimal viable ship, e.g. "T1 explo frigate (Heron/Probe/Imicus/Magnate)"
  ship_limit TEXT,               -- acceleration gate restriction or NULL
  ewar TEXT,                     -- e.g. "web, scram, neut" or NULL
  status TEXT NOT NULL,          -- active | removed | event | unverified
  escalation TEXT,
  loot_note TEXT,
  description TEXT,
  source_url TEXT,
  search_text TEXT NOT NULL      -- lowercase blob used for matching
);
CREATE TABLE IF NOT EXISTS site_enemies (
  id INTEGER PRIMARY KEY,
  site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  wave TEXT,
  ship_class TEXT NOT NULL,
  count_min INTEGER,
  count_max INTEGER,
  name TEXT,
  tier TEXT,
  ewar TEXT
);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_sites_name ON sites(name);
CREATE INDEX IF NOT EXISTS idx_sites_category ON sites(category);
CREATE INDEX IF NOT EXISTS idx_site_enemies_site ON site_enemies(site_id);
"""

CATEGORIES: tuple[str, ...] = (
    "combat_ded",
    "combat_unrated",
    "combat_anomaly",
    "data",
    "relic",
    "gas",
    "chemical_lab",
    "ghost",
    "sleeper_cache",
    "wormhole_combat",
    "wormhole_data",
    "wormhole_relic",
    "wormhole_gas",
    "wormhole_ore",
    "ore",
    "ice",
    "fw_complex",
    "insurgency",
    "homefront",
    "pochven",
    "drifter",
    "event",
    "wormhole_connection",
    "other",
)

SCAN_GROUPS: tuple[str, ...] = (
    "Combat Site",
    "Data Site",
    "Relic Site",
    "Gas Site",
    "Wormhole",
    "Ore Site",
    "Combat Anomaly",
    "Ore Anomaly",
    "Ice Anomaly",
    "Beacon",
)

DANGER_LABELS: tuple[str, ...] = ("n/a", "Safe", "Low", "Medium", "High", "Deadly")
"""Index == the ``danger`` integer (0..5)."""

STATUSES: tuple[str, ...] = ("active", "removed", "event", "unverified")


@dataclass(frozen=True, slots=True)
class Site:
    """One row of the ``sites`` table."""

    id: int
    name: str
    category: str
    scan_group: str
    is_signature: int
    space: str
    faction: str | None
    rating: str | None
    danger: int
    danger_label: str
    enemies: str
    min_ship: str
    ship_limit: str | None
    ewar: str | None
    status: str
    escalation: str | None
    loot_note: str | None
    description: str | None
    source_url: str | None
    search_text: str

    @classmethod
    def from_row(cls, row: sqlite3.Row | Mapping[str, object]) -> Site:
        """Build a :class:`Site` from a :class:`sqlite3.Row` (or any mapping)."""
        return cls(**{name: row[name] for name in SITE_COLUMNS})


SITE_COLUMNS: tuple[str, ...] = tuple(f.name for f in fields(Site))
"""Column names of ``sites`` in declaration order (also the ``Site`` fields)."""

ENEMY_COLUMNS: tuple[str, ...] = (
    "wave",
    "ship_class",
    "count_min",
    "count_max",
    "name",
    "tier",
    "ewar",
)
"""Writable columns of ``site_enemies`` (``id`` and ``site_id`` are implied)."""


def resolve_db_path(path: str | os.PathLike[str] | None = None) -> Path:
    """Return the DB path to use: explicit ``path`` > ``$EXPO_CATALOG_DB`` > default."""
    if path is not None:
        return Path(path)
    env = os.environ.get(ENV_VAR)
    return Path(env) if env else _PROJECT_DB_PATH


def connect(
    path: str | os.PathLike[str] | None = None,
    *,
    readonly: bool | None = None,
) -> sqlite3.Connection:
    """Open the catalog database.

    ``readonly`` defaults to ``True`` when the file already exists (the TUI
    only reads) and ``False`` otherwise, so the builder can create a fresh file
    with the same call. ``":memory:"`` is accepted for tests.
    Rows come back as :class:`sqlite3.Row`.
    """
    target = ":memory:" if path == ":memory:" else resolve_db_path(path)
    if target == ":memory:":
        conn = sqlite3.connect(":memory:")
    else:
        assert isinstance(target, Path)
        if readonly is None:
            readonly = target.exists()
        if readonly:
            conn = sqlite3.connect(f"{target.resolve().as_uri()}?mode=ro", uri=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes (idempotent)."""
    conn.executescript(SCHEMA)
    conn.commit()


def insert_site(conn: sqlite3.Connection, site: Site | Mapping[str, object]) -> int:
    """Insert one site and return its ``id``.

    Accepts a :class:`Site` or a mapping with the ``sites`` column names. An
    ``id`` of ``None`` (or a missing key) lets SQLite assign one.
    """
    data = {name: getattr(site, name) for name in SITE_COLUMNS} if isinstance(site, Site) else dict(site)
    if data.get("id") is None:
        data.pop("id", None)
    columns = [c for c in SITE_COLUMNS if c in data]
    placeholders = ", ".join(f":{c}" for c in columns)
    cur = conn.execute(
        f"INSERT INTO sites ({', '.join(columns)}) VALUES ({placeholders})",
        {c: data[c] for c in columns},
    )
    assert cur.lastrowid is not None
    return cur.lastrowid


def insert_enemy(conn: sqlite3.Connection, site_id: int, enemy: Mapping[str, object]) -> int:
    """Insert one ``site_enemies`` row for ``site_id`` and return its ``id``.

    ``enemy`` may contain any of :data:`ENEMY_COLUMNS`; ``ship_class`` is required.
    """
    data = {c: enemy.get(c) for c in ENEMY_COLUMNS}
    data["site_id"] = site_id
    columns = ["site_id", *ENEMY_COLUMNS]
    cur = conn.execute(
        f"INSERT INTO site_enemies ({', '.join(columns)}) VALUES ({', '.join(f':{c}' for c in columns)})",
        data,
    )
    assert cur.lastrowid is not None
    return cur.lastrowid


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Upsert one ``meta`` key/value pair."""
    conn.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def load_sites(conn: sqlite3.Connection) -> list[Site]:
    """All sites ordered by name (case-insensitive), then id."""
    rows = conn.execute(f"SELECT {', '.join(SITE_COLUMNS)} FROM sites ORDER BY name COLLATE NOCASE, id").fetchall()
    return [Site.from_row(row) for row in rows]


def load_enemies(conn: sqlite3.Connection, site_id: int) -> list[sqlite3.Row]:
    """``site_enemies`` rows for one site, in insertion order."""
    return conn.execute(
        "SELECT id, site_id, wave, ship_class, count_min, count_max, name, tier, ewar "
        "FROM site_enemies WHERE site_id = ? ORDER BY id",
        (site_id,),
    ).fetchall()


def load_all_enemies(conn: sqlite3.Connection) -> dict[int, list[sqlite3.Row]]:
    """Every ``site_enemies`` row grouped by ``site_id`` (one query)."""
    grouped: dict[int, list[sqlite3.Row]] = {}
    for row in conn.execute(
        "SELECT id, site_id, wave, ship_class, count_min, count_max, name, tier, ewar "
        "FROM site_enemies ORDER BY site_id, id"
    ):
        grouped.setdefault(row["site_id"], []).append(row)
    return grouped


def load_meta(conn: sqlite3.Connection) -> dict[str, str]:
    """The ``meta`` table as a plain dict."""
    return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM meta ORDER BY key")}
