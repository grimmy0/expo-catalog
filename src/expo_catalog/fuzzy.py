"""fzf-style fuzzy matching in pure Python.

Query syntax (fzf "extended" mode):

* whitespace separates terms; every term must match (AND)
* ``foo``   fuzzy subsequence match
* ``'foo``  exact substring match
* ``^foo``  prefix match, ``foo$`` suffix match, ``^foo$`` whole-text match
* ``!foo``  exclude texts containing ``foo`` (also ``!^foo`` / ``!foo$``)

Matching is case-insensitive. Scores follow fzf's spirit: each matched char
is worth :data:`SCORE_MATCH`, matches at word starts and consecutive runs earn
bonuses, gaps cost points, and longer texts lose a little.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Literal, TypeVar

__all__ = [
    "Term",
    "fuzzy_match",
    "parse_query",
    "rank",
]

T = TypeVar("T")

SCORE_MATCH = 16
SCORE_GAP_START = -3
SCORE_GAP_EXTENSION = -1
BONUS_BOUNDARY = 8
"""Match right after a word delimiter (``-``, ``(``, ``/``, ``_`` ...)."""
BONUS_BOUNDARY_WHITE = 10
"""Match right after whitespace."""
BONUS_TEXT_START = 12
"""Match at the very start of the text (prefix matches win ties)."""
BONUS_CONSECUTIVE = 4
BONUS_FIRST_CHAR_MULTIPLIER = 2
LENGTH_PENALTY_DIVISOR = 32
"""``len(text) // 32`` is subtracted from the final score (shorter wins ties)."""

_WORD_DELIMITERS = frozenset("-_()[]{}/\\.,:;'\"|")
_NEG = -(10**9)
_MAX_DP_CELLS = 4096
"""Above this many pattern×window cells the DP falls back to the tight window."""

TermKind = Literal["fuzzy", "exact", "prefix", "suffix", "equal"]


@dataclass(frozen=True, slots=True)
class Term:
    """One parsed query term."""

    text: str
    """Lower-cased body with the operators stripped."""
    kind: TermKind
    invert: bool = False


def parse_query(query: str) -> list[Term]:
    """Split ``query`` into :class:`Term` objects; operator-only tokens are dropped."""
    terms: list[Term] = []
    for raw in query.lower().split():
        body = raw
        invert = False
        exact = False
        if body.startswith("!"):
            invert = True
            body = body[1:]
        if body.startswith("'"):
            exact = True
            body = body[1:]
        anchor_start = body.startswith("^")
        if anchor_start:
            body = body[1:]
        anchor_end = body.endswith("$")
        if anchor_end:
            body = body[:-1]
        if not body:
            continue
        kind: TermKind
        if anchor_start and anchor_end:
            kind = "equal"
        elif anchor_start:
            kind = "prefix"
        elif anchor_end:
            kind = "suffix"
        elif exact or invert:
            # fzf: a bare `!foo` is an inverse *exact* match.
            kind = "exact"
        else:
            kind = "fuzzy"
        terms.append(Term(body, kind, invert))
    return terms


def _bonus_at(text: str, index: int) -> int:
    """Positional bonus for a match at ``text[index]``."""
    if index == 0:
        return BONUS_TEXT_START
    prev = text[index - 1]
    if prev.isspace():
        return BONUS_BOUNDARY_WHITE
    if prev in _WORD_DELIMITERS:
        return BONUS_BOUNDARY
    return 0


def _run_bonus(bonus: int) -> int:
    """Bonus a consecutive run inherits from its first char (fzf rule)."""
    return bonus if bonus >= BONUS_BOUNDARY else 0


def _substring_score(text: str, start: int, length: int) -> int:
    first = _bonus_at(text, start)
    return (
        length * SCORE_MATCH
        + first * BONUS_FIRST_CHAR_MULTIPLIER
        + (length - 1) * max(BONUS_CONSECUTIVE, _run_bonus(first))
    )


def _find_best_substring(text: str, needle: str) -> int:
    """Index of the occurrence of ``needle`` with the best positional bonus, or -1."""
    best = -1
    best_bonus = -1
    idx = text.find(needle)
    while idx >= 0:
        bonus = _bonus_at(text, idx)
        if bonus > best_bonus:
            best, best_bonus = idx, bonus
            if bonus >= BONUS_BOUNDARY_WHITE:
                break
        idx = text.find(needle, idx + 1)
    return best


def _fuzzy(pattern: str, text: str) -> tuple[int, list[int]] | None:
    """Optimal-ish subsequence alignment of ``pattern`` inside ``text``.

    Like fzf's v2 algorithm: a forward greedy pass proves a match exists and
    finds where the earliest match ends; a small dynamic programme over the
    window from the first occurrence of ``pattern[0]`` to that end then picks
    the alignment with the best score. Consecutive runs inherit the boundary
    bonus of the char that started the run, so ``gate`` in ``forgotten
    gateway`` beats ``g-a-t-e``.
    """
    # Forward pass: does a subsequence match exist at all? Where does it end?
    pos = -1
    first_pos = -1
    for ch in pattern:
        pos = text.find(ch, pos + 1)
        if pos < 0:
            return None
        if first_pos < 0:
            first_pos = pos
    end = pos
    start = first_pos
    if len(pattern) * (end - start + 1) > _MAX_DP_CELLS:
        # Pathologically wide window: fall back to the tight fzf-v1 window.
        start = end + 1
        for ch in reversed(pattern):
            start = text.rfind(ch, 0, start)
    window = text[start : end + 1]
    width = len(window)
    bonuses = [_bonus_at(text, start + j) for j in range(width)]

    # score[i][j]: best score with pattern[i] matched at window[j]
    # run[i][j]:   boundary bonus inherited by the consecutive run ending there
    # back[i][j]:  window index where pattern[i-1] was matched
    first = pattern[0]
    score_row = [_NEG] * width
    run_row = [0] * width
    for j in range(width):
        if window[j] == first:
            score_row[j] = SCORE_MATCH + bonuses[j] * BONUS_FIRST_CHAR_MULTIPLIER
            run_row[j] = _run_bonus(bonuses[j])
    scores = [score_row]
    runs = [run_row]
    back: list[list[int]] = [[-1] * width]
    for i in range(1, len(pattern)):
        pch = pattern[i]
        prev = scores[-1]
        prev_run = runs[-1]
        cur = [_NEG] * width
        cur_run = [0] * width
        cur_back = [-1] * width
        best_gap = _NEG  # best prev[k] for k <= j-2, gap penalty included
        best_gap_k = -1
        for j in range(1, width):
            if j >= 2:
                decayed = best_gap + SCORE_GAP_EXTENSION if best_gap > _NEG else _NEG
                fresh = prev[j - 2] + SCORE_GAP_START if prev[j - 2] > _NEG else _NEG
                if fresh >= decayed:
                    best_gap, best_gap_k = fresh, j - 2
                else:
                    best_gap = decayed
            if window[j] != pch:
                continue
            bonus = bonuses[j]
            consecutive = _NEG
            consecutive_run = 0
            if prev[j - 1] > _NEG:
                inherited = prev_run[j - 1]
                consecutive = prev[j - 1] + SCORE_MATCH + max(bonus, BONUS_CONSECUTIVE, inherited)
                consecutive_run = inherited or _run_bonus(bonus)
            gapped = best_gap + SCORE_MATCH + bonus if best_gap > _NEG else _NEG
            if consecutive >= gapped:
                if consecutive > _NEG:
                    cur[j] = consecutive
                    cur_run[j] = consecutive_run
                    cur_back[j] = j - 1
            else:
                cur[j] = gapped
                cur_run[j] = _run_bonus(bonus)
                cur_back[j] = best_gap_k
        scores.append(cur)
        runs.append(cur_run)
        back.append(cur_back)

    last = scores[-1]
    j = max(range(width), key=last.__getitem__)
    score = last[j]
    if score <= _NEG:  # pragma: no cover - the greedy pass guarantees a match
        return None
    positions: list[int] = []
    for i in range(len(pattern) - 1, -1, -1):
        positions.append(start + j)
        j = back[i][j]
    positions.reverse()
    return score, positions


def _match_term(term: Term, text: str) -> tuple[int, list[int]] | None:
    """Match one (non-inverted) term against lower-cased ``text``."""
    needle = term.text
    if term.kind == "fuzzy":
        return _fuzzy(needle, text)
    if term.kind == "exact":
        idx = _find_best_substring(text, needle)
    elif term.kind == "prefix":
        idx = 0 if text.startswith(needle) else -1
    elif term.kind == "suffix":
        idx = len(text) - len(needle) if text.endswith(needle) else -1
    else:  # equal
        idx = 0 if text == needle else -1
    if idx < 0:
        return None
    return _substring_score(text, idx, len(needle)), list(range(idx, idx + len(needle)))


def _match_terms(terms: list[Term], text: str) -> tuple[int, list[int]] | None:
    low = text.lower()
    total = 0
    positions: set[int] = set()
    for term in terms:
        found = _match_term(term, low)
        if term.invert:
            if found is not None:
                return None
            continue
        if found is None:
            return None
        total += found[0]
        positions.update(found[1])
    total -= len(low) // LENGTH_PENALTY_DIVISOR
    return total, sorted(positions)


def fuzzy_match(query: str, text: str) -> tuple[int, list[int]] | None:
    """Match ``query`` against ``text``.

    Returns ``(score, positions)`` where ``positions`` are the indices of the
    matched characters in ``text`` (sorted, de-duplicated), or ``None`` when
    any term fails. An empty query matches everything with score 0.
    """
    terms = parse_query(query)
    if not terms:
        return 0, []
    return _match_terms(terms, text)


def rank[T](query: str, items: Iterable[T], key: Callable[[T], str]) -> list[tuple[int, T]]:
    """Filter and sort ``items`` by how well ``key(item)`` matches ``query``.

    Result is sorted by score descending; ties keep the input order (the sort is
    stable), so pass items pre-sorted by name to get "score, then name". An
    empty query returns every item in input order with score 0.
    """
    terms = parse_query(query)
    if not terms:
        return [(0, item) for item in items]
    scored: list[tuple[int, T]] = []
    for item in items:
        found = _match_terms(terms, key(item))
        if found is not None:
            scored.append((found[0], item))
    scored.sort(key=lambda pair: -pair[0])
    return scored
