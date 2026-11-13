"""Command-line front end for the data pipeline.

    uv run python -m scraper fetch            # wiki -> data/raw (git-ignored), data/wiki_state.json, data/systems.json
    uv run python -m scraper parse            # data/raw -> data/parsed_sites.json
    uv run python -m scraper build [--out P]  # data/parsed_sites.json -> src/expo_catalog/data/catalog.sqlite
    uv run python -m scraper check [--json P] # compare the live wiki with data/wiki_state.json
    uv run python -m scraper refresh          # fetch -> parse -> build

The per-stage modules (``python -m scraper.fetch`` etc.) keep working as before.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

OUT_HELP = "output SQLite path (default src/expo_catalog/data/catalog.sqlite, the catalog bundled with the package)"


def cmd_fetch(_args: argparse.Namespace) -> int:
    from scraper import systems
    from scraper.wiki import fetch_all

    fetch_all()
    systems.refresh()  # resolve systems newly named on COSMOS pages (ESI) into data/systems.json
    return 0


def cmd_parse(_args: argparse.Namespace) -> int:
    from scraper.parse import main as parse_main

    parse_main()
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from scraper import build

    out = build.build(args.out)
    build.report(out)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    from scraper.check import run_check

    return run_check(args.json, args.write_state)


def cmd_refresh(args: argparse.Namespace) -> int:
    for name, fn in (("fetch", cmd_fetch), ("parse", cmd_parse), ("build", cmd_build)):
        print(f"== {name}")
        code = fn(args)
        if code:
            print(f"{name} failed with exit code {code}", file=sys.stderr)
            return code
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scraper", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch", help="download the wiki pages into data/raw").set_defaults(func=cmd_fetch)
    sub.add_parser("parse", help="parse data/raw into data/parsed_sites.json").set_defaults(func=cmd_parse)
    p_build = sub.add_parser("build", help="build src/expo_catalog/data/catalog.sqlite (the bundled catalog)")
    p_build.add_argument("--out", type=Path, default=None, help=OUT_HELP)
    p_build.set_defaults(func=cmd_build)
    p_check = sub.add_parser("check", help="report wiki changes since the last fetch (exit 1 if any)")
    p_check.add_argument("--json", type=Path, default=None, help="also write the report as JSON")
    p_check.add_argument("--write-state", action="store_true", help="overwrite data/wiki_state.json afterwards")
    p_check.set_defaults(func=cmd_check)
    p_refresh = sub.add_parser("refresh", help="fetch, parse and build in one go")
    p_refresh.add_argument("--out", type=Path, default=None, help=OUT_HELP)
    p_refresh.set_defaults(func=cmd_refresh)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except Exception as exc:  # surface a short message and a failing exit code for CI
        print(f"{args.command} failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
