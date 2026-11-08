# expo-catalog

A terminal UI catalog of every EVE Online cosmic signature and anomaly, with
fzf-style filtering. It covers known space, wormhole space (C1–C6, Thera,
shattered and Drifter systems) and Pochven: DED-rated and unrated combat
sites, data, relic and gas sites, ghost sites, sleeper caches, chemical labs,
combat/ore/ice anomalies, Faction Warfare complexes, insurgency and homefront
sites, incursions, wormhole connections and recurring event sites. Each entry
shows how dangerous the site is, what you will be shooting (or dodging) and the
smallest ship that can reasonably run it.

## Requirements

- Python 3.15
- [uv](https://docs.astral.sh/uv/)

## Run

```sh
uv run expo-catalog
```

The database ships in `data/catalog.sqlite`. Set `EXPO_CATALOG_DB` to point at
a different file. If the database is missing the command prints a hint and
exits with status 1.

### Keys

| Key | Action |
| --- | --- |
| type | filter the table live |
| `↑` / `↓`, `ctrl+k` / `ctrl+j` | move the highlighted row (the filter keeps focus) |
| `PageUp` / `PageDown` | page through the table |
| `Enter` | toggle the detail panel |
| `Esc` | clear the filter; quit when it is already empty |
| `ctrl+q` | quit |
| `F1` / `?` | help |

### Filter syntax

Terms are separated by spaces and must all match (AND). Matching is
case-insensitive and fuzzy by default; the best matches sort first, ties keep
alphabetical order.

| Term | Meaning |
| --- | --- |
| `serp outpost` | both terms match as subsequences |
| `'den` | exact substring |
| `!relic` | exclude texts containing `relic` |
| `^angel` | prefix match |
| `site$` | suffix match |

### Columns

- **Name**: exact in-game site name.
- **Danger**: a 0–5 bar coloured green to red.
  - `n/a` (0): no rating applies, e.g. wormhole connections.
  - `Safe` (1): no NPCs.
  - `Low` (2): a T1 frigate or destroyer handles it.
  - `Medium` (3): cruiser or battlecruiser territory.
  - `High` (4): battleship, T3 cruiser, marauder or a small gang.
  - `Deadly` (5): fleet-only or a capital-class threat.
- **Enemies**: NPC summary summed across all rooms and waves as documented on
  the wiki. The detail panel lists the per-wave rows.
- **Min ship**: the minimal viable ship for the site.

The detail panel (below the table) shows the full record: type, scan group,
whether it must be probed down, space, faction, rating, ship limit, EWAR,
status, escalation, loot note, description, source URL and the enemy waves.

## Data pipeline

```sh
uv run python -m scraper.fetch   # refresh data/raw from the EVE University wiki API (git-ignored)
uv run python -m scraper.parse   # data/raw -> data/parsed_sites.json
uv run python -m scraper.build   # data/parsed_sites.json -> data/catalog.sqlite
```

Sources:

- [EVE University wiki](https://wiki.eveuniversity.org) (CC-BY-SA) for site
  pages, NPC tables and escalations.
- EVE Ref reference data (derived from the SDE) for wormhole types.
- Hand-curated lists in `scraper/curated.py` for sites the wiki does not
  describe consistently.

Every site carries a `status`:

| status | Meaning |
| --- | --- |
| `active` | currently in the game |
| `removed` | no longer spawns, kept for reference |
| `event` | recurring or seasonal event site |
| `unverified` | known only from Singularity (test server) data or an uncertain name |

The schema lives in `src/expo_catalog/db.py` and is the single source of truth
for both the builder and the TUI.

## Tests

```sh
uv run pytest -q
```

Tests run offline; the TUI tests drive the app headless with Textual's
`App.run_test()`.

## Layout

```
expo-catalog/
├── src/expo_catalog/
│   ├── __init__.py   # `expo-catalog` entry point
│   ├── app.py        # Textual app (table, filter, detail panel)
│   ├── db.py         # SQLite schema + read/insert helpers
│   └── fuzzy.py      # fzf-style matcher
├── scraper/
│   ├── fetch.py      # download wiki pages into data/raw
│   ├── parse.py      # wiki text -> data/parsed_sites.json
│   ├── build.py      # parsed sites -> data/catalog.sqlite
│   ├── curated.py    # hand-maintained site lists
│   ├── rules.py      # classification / danger rules
│   └── wiki.py       # MediaWiki API client
├── data/
│   ├── catalog.sqlite
│   ├── parsed_sites.json
│   ├── wormholes.json
│   └── raw/          # git-ignored wiki cache
└── tests/
```
