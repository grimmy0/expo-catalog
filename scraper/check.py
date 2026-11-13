"""Detect EVE University wiki changes since the last fetch without downloading page content.

    uv run python -m scraper check [--json PATH] [--write-state]

Compares the live membership (tracked categories, ``wiki.EXTRA_PAGES`` and pages using a
site infobox template, see ``wiki.site_membership``) and latest revision ids with the committed
``data/wiki_state.json`` snapshot and reports NEW, REMOVED and CHANGED pages
(with wiki diff links). Changed pages that have a hand-written override in
``scraper.curated.OVERRIDES`` are flagged for re-review.

Exit codes: 0 nothing changed, 1 something changed, 2 error.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scraper import wiki

WIKI_INDEX = "https://wiki.eveuniversity.org/index.php"


@dataclass
class Change:
    title: str
    old_revid: int
    new_revid: int
    timestamp: str
    diff_url: str
    overridden: bool = False
    categories: list[str] = field(default_factory=list)


@dataclass
class Report:
    new: list[dict] = field(default_factory=list)  # {"title", "categories"}
    removed: list[dict] = field(default_factory=list)  # {"title", "reason"}
    changed: list[Change] = field(default_factory=list)
    flagged_overrides: list[str] = field(default_factory=list)
    unchanged: int = 0
    tracked: int = 0
    checked_at: str = ""

    @property
    def has_changes(self) -> bool:
        return bool(self.new or self.removed or self.changed)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["has_changes"] = self.has_changes
        return d

    def format_text(self) -> str:
        lines = [
            f"wiki check at {self.checked_at}: {self.tracked} tracked pages, {self.unchanged} unchanged, "
            f"{len(self.changed)} changed, {len(self.new)} new, {len(self.removed)} removed"
        ]
        if self.new:
            lines.append("NEW pages (in tracked categories or using a site infobox, not yet in the catalog):")
            lines += [f"  + {n['title']}  [{', '.join(n['categories']) or 'extra'}]" for n in self.new]
        if self.removed:
            lines.append("REMOVED pages (tracked, no longer in categories or deleted):")
            lines += [f"  - {r['title']}  ({r['reason']})" for r in self.removed]
        if self.changed:
            lines.append("CHANGED pages:")
            for c in self.changed:
                flag = "  [OVERRIDE - re-review curated.OVERRIDES]" if c.overridden else ""
                lines.append(f"  * {c.title}  r{c.old_revid} -> r{c.new_revid} ({c.timestamp}){flag}")
                lines.append(f"      {c.diff_url}")
        if self.flagged_overrides:
            lines.append("Hand overrides touched by changed pages: " + ", ".join(self.flagged_overrides))
        if not self.has_changes:
            lines.append("No changes.")
        return "\n".join(lines)


def diff_url(title: str, old_revid: int) -> str:
    return f"{WIKI_INDEX}?{urllib.parse.urlencode({'title': title, 'diff': 'cur', 'oldid': old_revid})}"


def compute_report(
    state: Mapping[str, Mapping],
    current: Mapping[str, list[str]],
    meta: Mapping[str, Mapping],
    overrides: Iterable[str] = (),
    checked_at: str = "",
) -> Report:
    """Pure comparison of the committed ``state`` with the live ``current`` membership and ``meta`` revisions.

    ``current`` is {title: categories} for every title that should be tracked now; ``meta`` holds the
    live revision info for every title in ``state`` ∪ ``current`` that still exists on the wiki.
    """
    overridden = set(overrides)
    report = Report(checked_at=checked_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    report.tracked = len(state)
    for title in sorted(current):
        if title not in state:
            report.new.append({"title": title, "categories": list(current[title])})
    for title in sorted(state):
        if title not in current:
            report.removed.append({"title": title, "reason": "no longer in a tracked category"})
            continue
        info = meta.get(title)
        if info is None:
            report.removed.append({"title": title, "reason": "page missing on the wiki"})
            continue
        old = int(state[title].get("revid", 0))
        new = int(info["revid"])
        if old != new:
            report.changed.append(
                Change(
                    title=title,
                    old_revid=old,
                    new_revid=new,
                    timestamp=str(info.get("timestamp", "")),
                    diff_url=diff_url(title, old),
                    overridden=title in overridden,
                    categories=list(current.get(title, [])),
                )
            )
        else:
            report.unchanged += 1
    report.flagged_overrides = sorted(c.title for c in report.changed if c.overridden)
    return report


def live_membership() -> dict[str, list[str]]:
    """{title: categories} the catalog should track now (same rules as ``wiki.fetch_all``)."""
    _rows, tracked = wiki.site_membership()
    return tracked


def state_from(current: Mapping[str, list[str]], meta: Mapping[str, Mapping]) -> dict[str, dict]:
    return {
        t: {"revid": int(meta[t]["revid"]), "timestamp": str(meta[t].get("timestamp", "")), "categories": list(cats)}
        for t, cats in current.items()
        if t in meta
    }


def run_check(json_path: Path | None = None, write_state: bool = False, state_path: Path = wiki.STATE_FILE) -> int:
    """Run the live check; returns the process exit code (0 unchanged, 1 changed, 2 error)."""
    from scraper import curated  # local import: curated pulls in rules, not needed for the pure comparison

    try:
        state = wiki.load_state(state_path)
        current = live_membership()
        meta = wiki.page_metadata(sorted(set(state) | set(current)))
    except Exception as exc:  # network / API problems
        print(f"check failed: {exc}", file=sys.stderr)
        return 2
    report = compute_report(state, current, meta, overrides=curated.OVERRIDES)
    print(report.format_text())
    if json_path is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report.to_dict(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {json_path}")
    if write_state:
        wiki.save_state(state_from(current, meta), state_path)
        print(f"wrote {state_path} ({len(current)} tracked pages)")
    return 1 if report.has_changes else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", type=Path, default=None, help="also write the report as JSON to this path")
    parser.add_argument(
        "--write-state",
        action="store_true",
        help="after reporting, overwrite data/wiki_state.json with the live revisions (metadata only)",
    )
    args = parser.parse_args(argv)
    return run_check(args.json, args.write_state)


if __name__ == "__main__":
    sys.exit(main())
