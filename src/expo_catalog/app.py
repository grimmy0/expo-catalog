"""Textual TUI for browsing the EVE exploration-site catalog."""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from os import PathLike

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import DataTable, Footer, Header, Input, Static

from expo_catalog import db
from expo_catalog.db import Site
from expo_catalog.fuzzy import rank

__all__ = [
    "Catalog",
    "CatalogApp",
    "COLUMNS",
    "PLACEHOLDER",
    "danger_cell",
    "load_catalog",
    "render_detail",
    "run",
]

PLACEHOLDER = "Type to filter… (fzf-style: space = AND, 'exact, !exclude, ^prefix)"
COLUMNS: tuple[str, ...] = ("Name", "Danger", "Enemies", "Min ship")
BUILD_COMMAND = "uv run python -m scraper.build"

HELP_TEXT = (
    "Type to filter (fzf syntax: space = AND, 'exact, !exclude, ^prefix, suffix$).\n"
    "↑/↓ or ctrl+k/ctrl+j move · PgUp/PgDn page · Enter toggles details\n"
    "Esc clears the filter (or quits when empty) · ctrl+q quits · F1 / ? help"
)

# danger 1..5 → green → red
_DANGER_STYLES: dict[int, str] = {
    1: "#3fb950",
    2: "#9ccc3c",
    3: "#e3b341",
    4: "#f0883e",
    5: "bold #f85149",
}

_CATEGORY_LABELS: dict[str, str] = {
    "combat_ded": "Combat (DED rated)",
    "combat_unrated": "Combat (unrated complex)",
    "combat_anomaly": "Combat anomaly",
    "data": "Data site",
    "relic": "Relic site",
    "gas": "Gas site",
    "chemical_lab": "Chemical lab (gas / booster)",
    "ghost": "Ghost site",
    "sleeper_cache": "Sleeper cache",
    "wormhole_combat": "Wormhole combat",
    "wormhole_data": "Wormhole data",
    "wormhole_relic": "Wormhole relic",
    "wormhole_gas": "Wormhole gas",
    "wormhole_ore": "Wormhole ore",
    "ore": "Ore site",
    "ice": "Ice belt",
    "fw_complex": "Faction Warfare complex",
    "insurgency": "Insurgency site",
    "homefront": "Homefront operation",
    "pochven": "Pochven site",
    "drifter": "Drifter site",
    "event": "Event site",
    "wormhole_connection": "Wormhole connection",
    "other": "Other",
}

_NAME_WIDTH = 44
_ENEMIES_WIDTH = 44
_SHIP_WIDTH = 36


def _clip(text: str, width: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


def danger_cell(danger: int, label: str) -> Text:
    """Render ``▮▮▮▯▯ Medium`` coloured green→red; 0 renders as dim ``n/a``."""
    if danger <= 0:
        return Text("n/a", style="dim")
    level = min(5, danger)
    bar = "▮" * level + "▯" * (5 - level)
    return Text(f"{bar} {label}", style=_DANGER_STYLES[level])


def _count(row: sqlite3.Row) -> str:
    lo, hi = row["count_min"], row["count_max"]
    if lo is None and hi is None:
        return ""
    if lo is None:
        return f"≤{hi}"
    if hi is None or hi == lo:
        return str(lo)
    return f"{lo}-{hi}"


def render_detail(site: Site, enemies: list[sqlite3.Row]) -> Text:
    """Full record for the detail panel."""
    out = Text()
    out.append(site.name, style="bold underline")
    out.append("\n")

    def field(label: str, value: object, *, style: str | None = None) -> None:
        shown = "—" if value in (None, "") else str(value)
        out.append(f"{label:<12}", style="bold dim")
        out.append(shown, style=style)
        out.append("\n")

    kind = _CATEGORY_LABELS.get(site.category, site.category.replace("_", " ").title())
    probe = (
        "Signature (must be probed down)"
        if site.is_signature
        else "Anomaly / beacon (shows on the scanner)"
    )
    field("Type", kind)
    field("Scan group", site.scan_group)
    field("Probe", probe)
    field("Space", site.space)
    field("Faction", site.faction)
    field("Rating", site.rating)
    out.append(f"{'Danger':<12}", style="bold dim")
    out.append_text(danger_cell(site.danger, site.danger_label))
    out.append("\n")
    field("Enemies", site.enemies)
    field("Min ship", site.min_ship)
    field("Ship limit", site.ship_limit)
    field("EWAR", site.ewar)
    field("Status", site.status)
    field("Escalation", site.escalation)
    field("Loot", site.loot_note)
    if site.description:
        out.append("\n")
        out.append(site.description.strip())
        out.append("\n")
    if site.source_url:
        out.append(f"{'Source':<12}", style="bold dim")
        out.append(site.source_url, style="underline")
        out.append("\n")
    if enemies:
        out.append("\nEnemy waves\n", style="bold")
        for row in enemies:
            wave = row["wave"] or "-"
            parts = [f"  {wave:<10}", f"{_count(row):>5} ", f"{row['ship_class']:<14}"]
            if row["name"]:
                parts.append(f" {row['name']}")
            if row["tier"]:
                parts.append(f" [{row['tier']}]")
            if row["ewar"]:
                parts.append(f"  EWAR: {row['ewar']}")
            out.append("".join(parts).rstrip())
            out.append("\n")
    out.rstrip()
    return out


@dataclass(slots=True)
class Catalog:
    """Everything the TUI needs, loaded once at startup."""

    sites: list[Site]
    enemies: dict[int, list[sqlite3.Row]]
    meta: dict[str, str]


def load_catalog(path: str | PathLike[str] | None = None) -> Catalog:
    """Read all sites, enemies and meta from the database at ``path``."""
    conn = db.connect(path)
    try:
        return Catalog(
            sites=db.load_sites(conn),
            enemies=db.load_all_enemies(conn),
            meta=db.load_meta(conn),
        )
    finally:
        conn.close()


class CatalogApp(App[None]):
    """fzf-style browser over the catalog."""

    TITLE = "EVE Exploration Catalog"

    CSS = """
    Screen {
        layout: vertical;
    }
    #filter {
        margin: 0 1;
    }
    #table {
        height: 1fr;
        margin: 0 1;
    }
    #status {
        height: 1;
        padding: 0 2;
        background: $panel;
        color: $text-muted;
    }
    #detail-pane {
        height: 40%;
        min-height: 6;
        max-height: 20;
        padding: 0 2;
        border-top: solid $primary;
        background: $surface;
    }
    #detail {
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("escape", "clear_or_quit", "Clear / quit"),
        Binding("enter", "toggle_detail", "Details", priority=True),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("ctrl+k", "cursor_up", "Up", show=False, priority=True),
        Binding("ctrl+j", "cursor_down", "Down", show=False, priority=True),
        Binding("pageup", "page_up", "Page up", show=False),
        Binding("pagedown", "page_down", "Page down", show=False),
        Binding("f1,question_mark", "help", "Help", key_display="F1", priority=True),
    ]

    def __init__(self, catalog: Catalog) -> None:
        super().__init__()
        self.catalog = catalog
        self.sites: list[Site] = catalog.sites
        self.filtered: list[Site] = list(catalog.sites)
        self._table_built = False
        self._row_cache: dict[int, tuple[str, Text, str, str]] = {}
        self._danger_cache: dict[tuple[int, str], Text] = {}
        built = catalog.meta.get("built_at") or catalog.meta.get("generated_at")
        self.sub_title = f"{len(self.sites)} sites" + (f" · built {built}" if built else "")

    # -- layout -----------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield Input(placeholder=PLACEHOLDER, id="filter")
        yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
        yield Static("", id="status")
        with VerticalScroll(id="detail-pane"):
            yield Static("", id="detail", markup=False)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#table", DataTable)
        table.add_columns(*COLUMNS)
        self._apply_filter("")
        self.query_one("#filter", Input).focus()

    # -- data -------------------------------------------------------------

    def _row_for(self, site: Site) -> tuple[str, Text, str, str]:
        cached = self._row_cache.get(site.id)
        if cached is None:
            key = (site.danger, site.danger_label)
            danger = self._danger_cache.get(key)
            if danger is None:
                danger = self._danger_cache[key] = danger_cell(*key)
            cached = self._row_cache[site.id] = (
                _clip(site.name, _NAME_WIDTH),
                danger,
                _clip(site.enemies, _ENEMIES_WIDTH),
                _clip(site.min_ship, _SHIP_WIDTH),
            )
        return cached

    def _apply_filter(self, query: str, *, force: bool = False) -> None:
        filtered = [site for _score, site in rank(query, self.sites, key=_search_key)]
        if not force and filtered == self.filtered and self._table_built:
            # Same rows in the same order (e.g. an operator-only token was
            # typed): skip the costly DataTable rebuild.
            return
        self.filtered = filtered
        table = self.query_one("#table", DataTable)
        table.clear()
        for site in filtered:
            table.add_row(*self._row_for(site), key=str(site.id))
        self._table_built = True
        table.move_cursor(row=0, column=0, scroll=True)
        self.query_one("#status", Static).update(
            f"{len(filtered)} / {len(self.sites)} sites"
        )
        self._show_detail(0)

    def _show_detail(self, row_index: int) -> None:
        detail = self.query_one("#detail", Static)
        if 0 <= row_index < len(self.filtered):
            site = self.filtered[row_index]
            detail.update(render_detail(site, self.catalog.enemies.get(site.id, [])))
        elif self.filtered:
            detail.update("")
        else:
            detail.update(Text("No sites match the filter.", style="dim italic"))

    # -- events -----------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        self._apply_filter(event.value)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._show_detail(event.cursor_row)

    # -- actions ----------------------------------------------------------

    def action_cursor_up(self) -> None:
        self.query_one("#table", DataTable).action_cursor_up()

    def action_cursor_down(self) -> None:
        self.query_one("#table", DataTable).action_cursor_down()

    def action_page_up(self) -> None:
        self.query_one("#table", DataTable).action_page_up()

    def action_page_down(self) -> None:
        self.query_one("#table", DataTable).action_page_down()

    def action_toggle_detail(self) -> None:
        pane = self.query_one("#detail-pane", VerticalScroll)
        pane.display = not pane.display

    def action_clear_or_quit(self) -> None:
        filter_input = self.query_one("#filter", Input)
        if filter_input.value:
            filter_input.clear()
            filter_input.focus()
        else:
            self.exit()

    def action_help(self) -> None:
        self.notify(HELP_TEXT, title="Help", timeout=10, markup=False)


def _search_key(site: Site) -> str:
    return site.search_text


def run(db_path: str | PathLike[str] | None = None) -> None:
    """Load the database and run the TUI.

    Exits with status 1 and a hint on stderr when the database is missing.
    A path given on the command line (``expo-catalog path/to.sqlite``) is used
    when ``db_path`` is not passed explicitly.
    """
    if db_path is None and len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        db_path = sys.argv[1]
    path = db.resolve_db_path(db_path)
    if not path.is_file():
        print(
            f"Database not found at {path} — run: {BUILD_COMMAND}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    CatalogApp(load_catalog(path)).run()
