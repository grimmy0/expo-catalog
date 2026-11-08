"""Tests for the fzf-style matcher."""

from __future__ import annotations

from expo_catalog.fuzzy import Term, fuzzy_match, parse_query, rank


def names(ranked):
    return [item for _score, item in ranked]


def test_subsequence_match_positions_and_case_insensitive():
    result = fuzzy_match("sph", "Serpentis Phi-Outpost")
    assert result is not None
    score, positions = result
    assert score > 0
    assert positions == [0, 10, 11]
    assert fuzzy_match("SERP", "serpentis") is not None


def test_no_subsequence_returns_none():
    assert fuzzy_match("xyz", "Serpentis Phi-Outpost") is None
    assert fuzzy_match("tsop", "outpost") is None  # order matters


def test_terms_are_anded():
    text = "serpentis phi-outpost combat ded 7/10"
    assert fuzzy_match("serp 7/10", text) is not None
    assert fuzzy_match("serp angel", text) is None


def test_exact_quote_requires_substring():
    assert fuzzy_match("'den", "hidden hideaway") is not None
    # "d-e-n" is a subsequence of "deadspace entrance" but not a substring
    assert fuzzy_match("den", "deadspace entrance") is not None
    assert fuzzy_match("'den", "deadspace entrance") is None


def test_exclude_bang():
    assert fuzzy_match("site !relic", "angel relic site") is None
    assert fuzzy_match("site !relic", "angel data site") is not None
    assert fuzzy_match("!^angel", "angel data site") is None
    assert fuzzy_match("!^angel", "local angel data site") is not None


def test_prefix_caret_and_suffix_dollar():
    assert fuzzy_match("^serp", "serpentis outpost") is not None
    assert fuzzy_match("^serp", "local serpentis outpost") is None
    assert fuzzy_match("post$", "serpentis outpost") is not None
    assert fuzzy_match("post$", "outpost serpentis") is None
    assert fuzzy_match("^angel$", "angel") is not None
    assert fuzzy_match("^angel$", "angels") is None


def test_operator_only_tokens_are_ignored():
    assert parse_query("! ' ^ $ ") == []
    assert parse_query("'exact !nope ^pre suf$ fuzzy") == [
        Term("exact", "exact"),
        Term("nope", "exact", invert=True),
        Term("pre", "prefix"),
        Term("suf", "suffix"),
        Term("fuzzy", "fuzzy"),
    ]


def test_word_start_beats_mid_word():
    at_boundary = fuzzy_match("ds", "drone data site")
    mid_word = fuzzy_match("ds", "hardsuit")
    assert at_boundary is not None and mid_word is not None
    assert at_boundary[0] > mid_word[0]
    # positions chosen are the word starts of "data" and "site"
    assert at_boundary[1] == [6, 11]


def test_consecutive_beats_scattered():
    consecutive = fuzzy_match("gate", "forgotten gateway")
    scattered = fuzzy_match("gate", "g-a-t-e scattered")
    assert consecutive is not None and scattered is not None
    assert consecutive[0] > scattered[0]


def test_prefix_beats_later_match_and_shorter_text_wins():
    prefix = fuzzy_match("angel", "angel hidden hideaway")
    later = fuzzy_match("angel", "hidden angel hideaway")
    assert prefix is not None and later is not None
    assert prefix[0] > later[0]
    short = fuzzy_match("angel", "angel")
    long = fuzzy_match("angel", "angel" + " x" * 40)
    assert short is not None and long is not None
    assert short[0] > long[0]


def test_empty_query_matches_everything_in_order():
    assert fuzzy_match("", "anything") == (0, [])
    assert fuzzy_match("   ", "anything") == (0, [])
    items = ["b", "a", "c"]
    assert rank("", items, key=str) == [(0, "b"), (0, "a"), (0, "c")]


def test_rank_filters_sorts_by_score_then_keeps_input_order():
    items = [
        "angel hidden hideaway",
        "guristas scout outpost",
        "serpentis hidden rally point",
        "hidden angel den",
    ]
    ranked = rank("hidden", items, key=str)
    assert names(ranked) == [
        "hidden angel den",  # prefix match scores highest
        "angel hidden hideaway",
        "serpentis hidden rally point",
    ]
    scores = [score for score, _ in ranked]
    assert scores == sorted(scores, reverse=True)
    assert names(rank("hidden !angel", items, key=str)) == ["serpentis hidden rally point"]


def test_rank_uses_key_callable():
    rows = [{"n": "Alpha", "t": "alpha one"}, {"n": "Beta", "t": "beta two"}]
    assert [row["n"] for _s, row in rank("two", rows, key=lambda r: r["t"])] == ["Beta"]
