"""Textual TUI for browsing the EVE exploration-site catalog."""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import metadata
from os import PathLike
from pathlib import Path

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header, Input, Static

from expo_catalog import db
from expo_catalog.db import Site
from expo_catalog.fuzzy import rank
from expo_catalog.labels import SPACE_WIDTH, TYPE_WIDTH, clip, space_label, type_label
from expo_catalog.query import parse_query

__all__ = [
    "COLUMNS",
    "HIDDEN_STATUSES",
    "PLACEHOLDER",
    "Catalog",
    "CatalogApp",
    "ColumnWidths",
    "build_parser",
    "compute_widths",
    "danger_cell",
    "load_catalog",
    "main",
    "refresh_catalog",
    "render_detail",
    "run",
    "space_label",
    "type_label",
]

PLACEHOLDER = "Type to filter… (fzf-style: space = AND, 'exact, !exclude; fields: space:c3 type:relic danger:<=3)"
COLUMNS: tuple[str, ...] = ("Name", "Type", "Space", "Danger", "Enemies", "Min ship")
BUILD_COMMAND = "uv run python -m scraper.build"
REFRESH_COMMAND: tuple[str, ...] = ("-m", "scraper", "refresh")
"""Arguments passed to ``sys.executable`` by ``--refresh`` (fetch → parse → build)."""

HIDDEN_STATUSES: frozenset[str] = frozenset({"removed", "unverified"})
"""Sites with one of these statuses are hidden until ctrl+r, ``--all`` or a ``status:`` term."""

HELP_TEXT = (
    "Type to filter (fzf syntax: space = AND, 'exact, !exclude, ^prefix, suffix$).\n"
    "Field terms narrow first: space:c3 type:relic danger:<=3 danger:2-4 ship:frig\n"
    "faction:angel name:den ewar:web status:removed · !space:null negates\n"
    "↑/↓ or ctrl+k/ctrl+j move · PgUp/PgDn page · Enter toggles details\n"
    "ctrl+r shows/hides removed + unverified sites (hidden by default)\n"
    "Esc clears the filter (or quits when empty) · ctrl+q quits · F1 / ? help\n"
    "Data: EVE University wiki (CC BY-SA 4.0) · unofficial, not affiliated with CCP"
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
    "cosmos": "COSMOS site",
    "event": "Event site",
    "wormhole_connection": "Wormhole connection",
    "other": "Other",
}

_DANGER_WIDTH = 12  # "▮▮▮▮▮ Medium"
_CELL_PADDING = 2  # DataTable default cell_padding=1 on both sides
_TABLE_CHROME = 4  # 1-col margin on each side + vertical scrollbar
_NAME_MIN = 34
_NAME_MAX = 49  # longest in-game site name


@dataclass(frozen=True, slots=True)
class ColumnWidths:
    """Clip widths for the content-sized columns at the current terminal width."""

    name: int
    enemies: int
    min_ship: int


def compute_widths(terminal_width: int) -> ColumnWidths:
    """Split the terminal width between Name, Enemies and Min ship.

    Type, Space and Danger are fixed; Name takes ~42% of what is left but
    never fewer than 34 columns, Enemies gets a bit more of the rest than
    Min ship. Below ~120 columns the table scrolls horizontally rather than
    squeezing Name further.
    """
    fixed = TYPE_WIDTH + SPACE_WIDTH + _DANGER_WIDTH + _CELL_PADDING * len(COLUMNS) + _TABLE_CHROME
    usable = terminal_width - fixed
    name = max(_NAME_MIN, min(_NAME_MAX, round(usable * 0.42)))
    rest = max(usable - name, 24)
    enemies = max(12, round(rest * 0.55))
    min_ship = max(10, rest - enemies)
    return ColumnWidths(name, enemies, min_ship)


def _cell(text: str, style: str = "") -> Text:
    """Plain (markup-free) single-line cell."""
    return Text(text, style=style, no_wrap=True, overflow="ellipsis", end="")


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
    probe = "Signature (must be probed down)" if site.is_signature else "Anomaly / beacon (shows on the scanner)"
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
        Binding(
            "ctrl+r",
            "toggle_hidden",
            "Hidden",
            tooltip="Show or hide removed and unverified sites",
            priority=True,
        ),
    ]

    def __init__(self, catalog: Catalog, *, show_hidden: bool = False) -> None:
        super().__init__()
        self.catalog = catalog
        self.sites: list[Site] = catalog.sites
        self.filtered: list[Site] = list(catalog.sites)
        self.show_hidden = show_hidden
        """Whether sites with a status in :data:`HIDDEN_STATUSES` are listed (toggled by ctrl+r)."""
        self._table_built = False
        self._widths = compute_widths(120)
        self._resize_timer: Timer | None = None
        self._row_cache: dict[int, tuple[Text, ...]] = {}
        self._danger_cache: dict[tuple[int, str], Text] = {}
        self._type_cache: dict[str, Text] = {}
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
        table.add_column("Name", key="name")
        table.add_column("Type", width=TYPE_WIDTH, key="type")
        table.add_column("Space", width=SPACE_WIDTH, key="space")
        table.add_column("Danger", key="danger")
        table.add_column("Enemies", key="enemies")
        table.add_column("Min ship", key="min_ship")
        self._widths = compute_widths(self.size.width or 120)
        self._apply_filter("")
        self.query_one("#filter", Input).focus()

    # -- data -------------------------------------------------------------

    def _row_for(self, site: Site) -> tuple[Text, ...]:
        cached = self._row_cache.get(site.id)
        if cached is None:
            key = (site.danger, site.danger_label)
            danger = self._danger_cache.get(key)
            if danger is None:
                danger = self._danger_cache[key] = danger_cell(*key)
            kind = type_label(site)
            kind_cell = self._type_cache.get(kind)
            if kind_cell is None:
                kind_cell = self._type_cache[kind] = _cell(kind, "dim")
            widths = self._widths
            cached = self._row_cache[site.id] = (
                _cell(clip(site.name, widths.name)),
                kind_cell,
                _cell(space_label(site.space), "dim"),
                danger,
                _cell(clip(site.enemies, widths.enemies)),
                _cell(clip(site.min_ship, widths.min_ship)),
            )
        return cached

    def _apply_filter(self, text: str, *, force: bool = False) -> None:
        query = parse_query(text)
        candidates = [site for site in self.sites if query.matches(site)] if query.filters else self.sites
        ranked = [site for _score, site in rank(query.plain, candidates, key=_search_key)]
        if self.show_hidden or query.has_field("status"):
            # An explicit status: term overrides the default hiding.
            filtered, hidden = ranked, 0
        else:
            filtered = [site for site in ranked if site.status not in HIDDEN_STATUSES]
            hidden = len(ranked) - len(filtered)
        status = f"{len(filtered)} / {len(self.sites)} sites"
        if hidden:
            status += f" · {hidden} hidden (ctrl+r)"
        self.query_one("#status", Static).update(status)
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

    def on_resize(self, event: events.Resize) -> None:
        # Debounce: terminals emit a burst of resizes while dragging.
        if self._resize_timer is not None:
            self._resize_timer.stop()
        self._resize_timer = self.set_timer(0.15, self._fit_columns)

    def _fit_columns(self) -> None:
        """Re-clip the content columns if the terminal width changed."""
        self._resize_timer = None
        widths = compute_widths(self.size.width or 120)
        if widths == self._widths or not self._table_built:
            return
        self._widths = widths
        self._row_cache.clear()
        table = self.query_one("#table", DataTable)
        row = table.cursor_row
        self._apply_filter(self.query_one("#filter", Input).value, force=True)
        table.move_cursor(row=row, column=0)

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

    def action_toggle_hidden(self) -> None:
        self.show_hidden = not self.show_hidden
        self._apply_filter(self.query_one("#filter", Input).value)

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


def run(db_path: str | PathLike[str] | None = None, *, show_hidden: bool = False) -> None:
    """Load the database and run the TUI.

    ``db_path`` falls back to ``$EXPO_CATALOG_DB`` and then the catalog bundled
    with the package (:data:`expo_catalog.db.PACKAGE_DB_PATH`). Exits with
    status 1 and a hint on stderr when the database is missing. ``show_hidden``
    starts with removed and unverified sites listed (the ``--all`` flag).
    """
    path = db.resolve_db_path(db_path)
    if not path.is_file():
        print(
            f"Database not found at {path} — run: {BUILD_COMMAND}",
            file=sys.stderr,
        )
        raise SystemExit(1)
    CatalogApp(load_catalog(path), show_hidden=show_hidden).run()


# -- command line -------------------------------------------------------------


def _package_version() -> str:
    try:
        return metadata.version("expo-catalog")
    except metadata.PackageNotFoundError:
        return "unknown"


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for the ``expo-catalog`` entry point."""
    parser = argparse.ArgumentParser(
        prog="expo-catalog",
        description="Browse every EVE Online cosmic signature and anomaly with fzf-style filtering.",
    )
    parser.add_argument(
        "--db",
        metavar="PATH",
        help=f"SQLite catalog to open (default: ${db.ENV_VAR} if set, else {db.DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="start with removed and unverified sites listed (ctrl+r toggles them in the TUI)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help=(
            "rebuild the catalog first: runs `python -m scraper refresh` (fetch → parse → build) "
            "in the source checkout; needs an editable install or `uv run`, exits 2 otherwise"
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {_package_version()}")
    return parser


def refresh_catalog(repo_root: str | PathLike[str] | None = None) -> None:
    """Run the scraper pipeline in ``repo_root`` (default: :data:`expo_catalog.db.REPO_ROOT`).

    Only works from a source checkout (``uv run`` or an editable install): the
    pipeline writes the bundled database in place. Exits 2 when there is no
    ``scraper/`` package to run and 1 when the pipeline itself fails.
    """
    root = Path(repo_root) if repo_root is not None else db.REPO_ROOT
    if not (root / "scraper" / "__init__.py").is_file():
        print(
            f"Cannot refresh: {root} is not a source checkout (no scraper/ package). "
            "Installed copies pick up new data when reinstalled: uv tool upgrade expo-catalog",
            file=sys.stderr,
        )
        raise SystemExit(2)
    print("Refreshing catalog (fetch → parse → build)…", file=sys.stderr)
    result = subprocess.run([sys.executable, *REFRESH_COMMAND], cwd=root)
    if result.returncode != 0:
        print(f"Refresh failed: scraper exited with code {result.returncode}", file=sys.stderr)
        raise SystemExit(1)


def main(argv: Sequence[str] | None = None) -> None:
    """Entry point: parse flags, optionally refresh, then launch the TUI."""
    args = build_parser().parse_args(argv)
    if args.refresh:
        refresh_catalog()
    run(args.db, show_hidden=args.all)
