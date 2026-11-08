"""Tests for scraper.check (wiki change detection) with the MediaWiki API mocked."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scraper import check, wiki


class FakeApi:
    """Answers categorymembers and revisions queries from in-memory data."""

    def __init__(self, members: dict[str, list[str]], revisions: dict[str, tuple[int, str]]):
        self.members = members  # category -> titles
        self.revisions = revisions  # title -> (revid, timestamp)
        self.calls: list[dict] = []

    def __call__(self, params: dict) -> dict:
        self.calls.append(params)
        if params.get("list") == "categorymembers":
            cat = params["cmtitle"].removeprefix("Category:")
            return {"query": {"categorymembers": [{"title": t} for t in self.members.get(cat, [])]}}
        if params.get("prop") == "revisions":
            assert "content" not in params["rvprop"], "check must not download page content"
            pages = []
            for title in params["titles"].split("|"):
                if title in self.revisions:
                    revid, ts = self.revisions[title]
                    pages.append({"title": title, "revisions": [{"revid": revid, "timestamp": ts}]})
                else:
                    pages.append({"title": title, "missing": True})
            return {"query": {"pages": pages}}
        raise AssertionError(f"unexpected API call {params}")


@pytest.fixture
def quiet_sleep(monkeypatch):
    monkeypatch.setattr(check.time, "sleep", lambda _s: None)
    monkeypatch.setattr(wiki.time, "sleep", lambda _s: None)


def test_compute_report_detects_new_removed_changed_and_flags_overrides():
    state = {
        "Angel Hideaway": {"revid": 10, "timestamp": "2026-01-01T00:00:00Z", "categories": ["Combat_Anomalies"]},
        "Old Site": {"revid": 5, "timestamp": "2025-01-01T00:00:00Z", "categories": ["Data_sites"]},
        "Deleted Site": {"revid": 7, "timestamp": "2025-01-01T00:00:00Z", "categories": ["Relic_sites"]},
        "Rampant Drone Fabricator": {"revid": 20, "timestamp": "2026-01-01T00:00:00Z", "categories": []},
    }
    current = {
        "Angel Hideaway": ["Combat_Anomalies"],
        "Brand New Site": ["Gas_sites"],
        "Deleted Site": ["Relic_sites"],
        "Rampant Drone Fabricator": [],
    }
    meta = {
        "Angel Hideaway": {"revid": 10, "timestamp": "2026-01-01T00:00:00Z"},
        "Brand New Site": {"revid": 99, "timestamp": "2026-11-01T00:00:00Z"},
        "Rampant Drone Fabricator": {"revid": 21, "timestamp": "2026-10-01T00:00:00Z"},
    }
    report = check.compute_report(state, current, meta, overrides={"Rampant Drone Fabricator"}, checked_at="t")
    assert [n["title"] for n in report.new] == ["Brand New Site"]
    assert sorted(r["title"] for r in report.removed) == ["Deleted Site", "Old Site"]
    reasons = {r["title"]: r["reason"] for r in report.removed}
    assert reasons["Deleted Site"] == "page missing on the wiki"
    assert reasons["Old Site"] == "no longer in a tracked category"
    assert len(report.changed) == 1
    change = report.changed[0]
    assert change.title == "Rampant Drone Fabricator" and change.old_revid == 20 and change.new_revid == 21
    assert change.overridden is True
    assert change.diff_url == (
        "https://wiki.eveuniversity.org/index.php?title=Rampant+Drone+Fabricator&diff=cur&oldid=20"
    )
    assert report.flagged_overrides == ["Rampant Drone Fabricator"]
    assert report.unchanged == 1 and report.has_changes
    text = report.format_text()
    assert "+ Brand New Site" in text and "OVERRIDE" in text and "diff=cur&oldid=20" in text
    as_json = report.to_dict()
    assert as_json["has_changes"] is True and as_json["changed"][0]["overridden"] is True


def test_compute_report_no_changes():
    state = {"A": {"revid": 1, "timestamp": "", "categories": ["X"]}}
    report = check.compute_report(state, {"A": ["X"]}, {"A": {"revid": 1, "timestamp": ""}}, checked_at="t")
    assert not report.has_changes and report.unchanged == 1
    assert report.format_text().endswith("No changes.")


def test_run_check_exit_codes_and_json(monkeypatch, tmp_path: Path, quiet_sleep):
    monkeypatch.setattr(wiki, "SITE_CATEGORIES", ("Data_sites",))
    monkeypatch.setattr(wiki, "EXTRA_PAGES", ("Extra Page",))
    fake = FakeApi(
        members={"Data_sites": ["Site A", "Site B"]},
        revisions={
            "Site A": (100, "2026-11-01T00:00:00Z"),
            "Site B": (200, "2026-11-02T00:00:00Z"),
            "Extra Page": (300, "2026-11-03T00:00:00Z"),
        },
    )
    monkeypatch.setattr(wiki, "api", fake)
    state_path = tmp_path / "wiki_state.json"

    # No state yet: everything is new -> exit 1, and --write-state bootstraps the snapshot.
    assert check.run_check(json_path=tmp_path / "r.json", write_state=True, state_path=state_path) == 1
    report = json.loads((tmp_path / "r.json").read_text())
    assert sorted(n["title"] for n in report["new"]) == ["Extra Page", "Site A", "Site B"]
    state = json.loads(state_path.read_text())
    assert state["Site A"] == {"revid": 100, "timestamp": "2026-11-01T00:00:00Z", "categories": ["Data_sites"]}
    assert state["Extra Page"]["categories"] == []

    # Same wiki -> nothing changed -> exit 0.
    assert check.run_check(state_path=state_path) == 0

    # Edit one page, add one, drop one -> exit 1 with the right report.
    fake.revisions["Site A"] = (101, "2026-11-05T00:00:00Z")
    fake.members["Data_sites"] = ["Site A", "Site C"]
    fake.revisions["Site C"] = (400, "2026-11-05T00:00:00Z")
    assert check.run_check(json_path=tmp_path / "r2.json", state_path=state_path) == 1
    report = json.loads((tmp_path / "r2.json").read_text())
    assert [c["title"] for c in report["changed"]] == ["Site A"]
    assert [n["title"] for n in report["new"]] == ["Site C"]
    assert [r["title"] for r in report["removed"]] == ["Site B"]
    # The state file is untouched without --write-state.
    assert json.loads(state_path.read_text())["Site A"]["revid"] == 100


def test_run_check_returns_2_on_api_error(monkeypatch, tmp_path: Path, quiet_sleep):
    def boom(_params):
        raise OSError("network down")

    monkeypatch.setattr(wiki, "api", boom)
    assert check.run_check(state_path=tmp_path / "missing.json") == 2


def test_page_metadata_follows_redirects_and_skips_missing(monkeypatch, quiet_sleep):
    def api(params):
        assert params["rvprop"] == "ids|timestamp"
        return {
            "query": {
                "redirects": [{"from": "Old Name", "to": "New Name"}],
                "pages": [
                    {"title": "New Name", "revisions": [{"revid": 42, "timestamp": "2026-01-01T00:00:00Z"}]},
                    {"title": "Gone", "missing": True},
                ],
            }
        }

    monkeypatch.setattr(wiki, "api", api)
    meta = wiki.page_metadata(["Old Name", "Gone"])
    assert meta == {"Old Name": {"revid": 42, "timestamp": "2026-01-01T00:00:00Z", "title": "New Name"}}


def test_tracked_titles_merges_categories_and_extras(monkeypatch):
    monkeypatch.setattr(wiki, "EXTRA_PAGES", ("Extra",))
    rows = [("Data_sites", "A"), ("Relic_sites", "A"), ("Gas_sites", "B")]
    assert wiki.tracked_titles(rows) == {"A": ["Data_sites", "Relic_sites"], "B": ["Gas_sites"], "Extra": []}


def test_cli_dispatch(monkeypatch):
    from scraper import __main__ as cli

    called: dict[str, object] = {}

    def fake_check(args):
        called["check"] = args.json
        return 0

    monkeypatch.setattr(cli, "cmd_check", fake_check)
    assert cli.main(["check", "--json", "out.json"]) == 0
    assert str(called["check"]) == "out.json"
    with pytest.raises(SystemExit):
        cli.main([])
