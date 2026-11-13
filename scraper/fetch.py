"""CLI entry point: ``uv run python -m scraper.fetch`` refreshes the raw wiki cache (and data/systems.json)."""

from __future__ import annotations

from scraper import systems
from scraper.wiki import fetch_all

if __name__ == "__main__":
    fetch_all()
    systems.refresh()
