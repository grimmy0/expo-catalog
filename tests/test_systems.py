"""Tests for scraper.systems (COSMOS system lookup) with ESI mocked."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scraper import systems


@pytest.mark.parametrize(
    ("security", "region", "expected"),
    [
        (1.0, "", "High"),
        (0.5092, "", "High"),
        (0.45, "", "High"),  # shown in game as 0.5
        (0.4499, "", "Low"),
        (0.05, "", "Low"),
        (0.0001, "", "Low"),  # shown as 0.1, still low-sec
        (0.0, "", "Null"),
        (-0.0436, "", "Null"),
        (-1.0, "Pochven", "Pochven"),
    ],
)
def test_security_class(security, region, expected):
    assert systems.security_class(security, region) == expected


def test_bands_and_space_labels():
    assert systems.bands(0.9, 0.4659) == "High"  # 0.4659 rounds to 0.5
    assert systems.bands(0.9, 0.4) == "High, Low"
    assert systems.bands(-0.19, -0.41) == "Null"
    assert systems.bands(0.6, -0.2) == "High, Low, Null"
    assert systems.space_label({"name": "Hjoramold", "security": 0.5092, "region": "Metropolis"}) == (
        "High (Hjoramold, Metropolis)"
    )
    assert systems.space_label({"name": "PPG-XC", "security": -0.0436, "region": "Cloud Ring"}) == (
        "Null (PPG-XC, Cloud Ring)"
    )
    constellation = {
        "name": "E-8CSQ",
        "kind": "constellation",
        "security": -0.19,
        "min_security": -0.41,
        "region": "Vale of the Silent",
    }
    assert systems.space_label(constellation) == "Null (E-8CSQ constellation, Vale of the Silent)"


def test_lookup_takes_the_first_known_candidate_case_insensitively():
    table = {
        "Hjoramold": {"security": 0.5, "region": "Metropolis"},
        "PPG-XC": {"security": -0.04, "region": "Cloud Ring"},
    }
    assert systems.lookup(["Caldari", "ppg-xc", "Hjoramold"], table) == {
        "name": "PPG-XC",
        "security": -0.04,
        "region": "Cloud Ring",
    }
    assert systems.lookup(["Nowhere"], table) is None


class FakeEsi:
    def __init__(self):
        self.calls: list[tuple[str, object]] = []

    def __call__(self, path, body=None):
        self.calls.append((path, body))
        if path == "/universe/ids/":
            names = set(body)
            out = {"systems": [], "constellations": []}
            if "Hjoramold" in names:
                out["systems"].append({"id": 30002075, "name": "Hjoramold"})
            if "E-8CSQ" in names:
                out["constellations"].append({"id": 20000400, "name": "E-8CSQ"})
            return out
        routes = {
            "/universe/systems/30002075/": {"security_status": 0.509212, "constellation_id": 20000305},
            "/universe/systems/1/": {"security_status": -0.19, "constellation_id": 20000400},
            "/universe/systems/2/": {"security_status": -0.41, "constellation_id": 20000400},
            "/universe/constellations/20000305/": {"region_id": 10000042, "systems": [30002075]},
            "/universe/constellations/20000400/": {"region_id": 10000039, "systems": [1, 2]},
            "/universe/regions/10000042/": {"name": "Metropolis"},
            "/universe/regions/10000039/": {"name": "Vale of the Silent"},
        }
        return routes[path]


@pytest.fixture
def fake_esi(monkeypatch):
    fake = FakeEsi()
    monkeypatch.setattr(systems, "esi", fake)
    monkeypatch.setattr(systems.time, "sleep", lambda _s: None)
    return fake


def test_resolve_systems_and_constellations(fake_esi):
    out = systems.resolve(["Hjoramold", "E-8CSQ", "Caldari", "Hjoramold"])
    assert out == {
        "Hjoramold": {"security": 0.5092, "region": "Metropolis"},
        "E-8CSQ": {"kind": "constellation", "security": -0.19, "min_security": -0.41, "region": "Vale of the Silent"},
    }
    # One name lookup for everything; each region name fetched once.
    assert [c for c in fake_esi.calls if c[0] == "/universe/ids/"] == [
        ("/universe/ids/", ["Caldari", "E-8CSQ", "Hjoramold"])
    ]
    assert sum(1 for p, _ in fake_esi.calls if p.startswith("/universe/regions/")) == 2


def test_refresh_adds_new_names_and_drops_unused(fake_esi, monkeypatch, tmp_path: Path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    (wiki_dir / "Maru_Prison_Facility.wiki").write_text(
        "<!-- TITLE: Maru Prison Facility -->\n{{CMBSiteInfo\n|type=COSMOS\n|location=Hjoramold\n}}\n"
        "[[Category:COSMOS sites]]\n",
        encoding="utf-8",
    )
    (wiki_dir / "Angel_Vigil.wiki").write_text(  # not a COSMOS page: never looked at
        "<!-- TITLE: Angel Vigil -->\n{{CMBSiteInfo\n|location=Old Man Star\n}}\n", encoding="utf-8"
    )
    monkeypatch.setattr(systems, "load_category_index", lambda: {})
    path = tmp_path / "systems.json"
    path.write_text(json.dumps({"Gone": {"security": 0.9, "region": "Nowhere"}}), encoding="utf-8")
    assert systems.refresh(wiki_dir, path) == 1
    assert json.loads(path.read_text()) == {"Hjoramold": {"security": 0.5092, "region": "Metropolis"}}
    # Second run: nothing new to resolve beyond the unresolved junk candidates.
    fake_esi.calls.clear()
    assert systems.refresh(wiki_dir, path) == 0
    assert all(p == "/universe/ids/" for p, _ in fake_esi.calls)


def test_tracked_table_covers_the_cached_cosmos_systems():
    table = systems.load_systems()
    assert {"Hjoramold", "PPG-XC", "Otomainen"} <= set(table)
    assert "Vale" not in table  # region-name word, not a COSMOS location
    for name, info in table.items():
        assert isinstance(info["security"], float) and info["region"], name
