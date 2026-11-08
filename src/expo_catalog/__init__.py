"""expo-catalog: a TUI catalog of every EVE Online cosmic signature and anomaly."""

from __future__ import annotations


def main() -> None:
    """Console-script entry point (``expo-catalog [--db PATH] [--refresh] [--version]``)."""
    from expo_catalog.app import main as app_main

    app_main()
