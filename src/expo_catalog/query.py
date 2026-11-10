"""Field filters for the filter box: ``space:c3 type:relic danger:<=3 forgotten``.

The typed text is split on whitespace into *field terms* and *plain terms*.
A field term is ``field:value`` (no spaces inside the value) with one of the
names in :data:`FIELDS`; ``!field:value`` negates it. Field terms narrow the
candidate sites before ranking. Everything else is a plain term and is handed,
joined with spaces, to :func:`expo_catalog.fuzzy.rank`, so the fzf operators
(``'exact``, ``!exclude``, ``^prefix``, ``suffix$``) and the ranking are
unchanged. A token with an unknown field name (``foo:bar``) is a plain term;
a known field with an empty value (``space:``) is dropped, like fzf drops
operator-only tokens. Matching is case-insensitive.

Fields:

* ``space:`` — substring of the Space text, or one of the tokens from
  :func:`space_tokens` (``high``, ``low``, ``null``, ``wormhole``, ``c1``..``c6``,
  ``c13``, ``thera``, ``shattered``, ``pochven``, ``drifter``), with the aliases
  ``hs``/``ls``/``ns`` (high/low/null), ``wh``/``j-space``/``w-space``
  (wormhole) and ``k-space`` (high, low or null). A generic ``Wormhole`` site
  matches any class, and ``space:wormhole`` matches every classed site.
  Sites whose space is ``Any``, ``Various`` or ``Unknown`` match everything.
* ``type:`` — substring of the Type column label (``DED 3/10``, ``WH relic``,
  ``Anom T4`` ...), the category (``combat ded``, ``wormhole relic``), the scan
  group (``Combat Site``, ``Data Site`` ...) or the rating.
* ``danger:`` — ``3``, ``<=3``, ``>=4``, ``<3``, ``>2``, ``=3`` or the inclusive
  range ``2-4``; a danger label (``safe``, ``low``, ``medium``, ``high``,
  ``deadly``, ``n/a``) may stand in for a number anywhere. Invalid values match
  nothing.
* ``ship:``, ``status:``, ``faction:``, ``name:``, ``ewar:`` — substring of the
  corresponding column; a NULL column never matches.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass

from expo_catalog import db
from expo_catalog.db import Site
from expo_catalog.labels import type_label

__all__ = [
    "FIELDS",
    "FieldFilter",
    "Query",
    "parse_query",
    "space_tokens",
]

# -- space ----------------------------------------------------------------------

CLASS_TOKENS: frozenset[str] = frozenset({"c1", "c2", "c3", "c4", "c5", "c6", "c13"})
"""Wormhole class tokens (C13 is the small-ship shattered class)."""

WILDCARD = "*"
"""Token of a site whose space is ``Any``, ``Various`` or ``Unknown``: it matches every ``space:`` term."""

_CLASS_NUMBERS = frozenset(int(token[1:]) for token in CLASS_TOKENS)
_WH_KINDS = CLASS_TOKENS | {"thera", "shattered"}
"""Values that a generic ``Wormhole`` site matches, and that make ``space:wormhole`` match a site."""
_WH_SPECIFIC = _WH_KINDS | {"drifter"}
"""Tokens that make a wormhole site *specific* (a bare ``Wormhole`` means any class)."""

_SPACE_WORDS: dict[str, tuple[str, ...]] = {
    "high": ("high",),
    "highsec": ("high",),
    "high-sec": ("high",),
    "low": ("low",),
    "lowsec": ("low",),
    "low-sec": ("low",),
    "null": ("null",),
    "nullsec": ("null",),
    "null-sec": ("null",),
    "k-space": ("high", "low", "null"),
    "kspace": ("high", "low", "null"),
    "wormhole": ("wormhole",),
    "wormholes": ("wormhole",),
    "w-space": ("wormhole",),
    "j-space": ("wormhole",),
    "pochven": ("pochven",),
    "thera": ("thera",),
    "shattered": ("shattered",),
    "drifter": ("drifter",),
    "any": (WILDCARD,),
    "various": (WILDCARD,),
    "unknown": (WILDCARD,),
}
_SPACE_ALIASES: dict[str, frozenset[str]] = {
    "hs": frozenset({"high"}),
    "ls": frozenset({"low"}),
    "ns": frozenset({"null"}),
    "highsec": frozenset({"high"}),
    "lowsec": frozenset({"low"}),
    "nullsec": frozenset({"null"}),
    "high-sec": frozenset({"high"}),
    "low-sec": frozenset({"low"}),
    "null-sec": frozenset({"null"}),
    "k-space": frozenset({"high", "low", "null"}),
    "kspace": frozenset({"high", "low", "null"}),
    "wh": frozenset({"wormhole"}),
    "j-space": frozenset({"wormhole"}),
    "w-space": frozenset({"wormhole"}),
}
"""Query-side aliases: ``space:hs`` means ``space:high`` ..."""

_WORD = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_CLASS_RANGE = re.compile(r"^c(\d{1,2})(?:-c?(\d{1,2}))?$")


def space_tokens(space: str) -> frozenset[str]:
    """Normalised tokens of a Space value.

    ``"High, Low"`` → ``{high, low}``; ``"C1-C4"`` → ``{c1, c2, c3, c4}``;
    ``"K-space (High, Low, Null)"`` → ``{high, low, null}``; ``"Wormhole C2-C6"``
    → ``{wormhole, c2, ..., c6}``; ``"Any (small-ship wormhole)"`` →
    ``{*, wormhole}``. Region names and other free text yield no tokens (they
    are still reachable through the substring rule of ``space:``).
    """
    tokens: set[str] = set()
    for word in _WORD.findall(space.lower()):
        mapped = _SPACE_WORDS.get(word)
        if mapped is not None:
            tokens.update(mapped)
            continue
        match = _CLASS_RANGE.match(word)
        if match is None:
            continue
        low = int(match.group(1))
        high = int(match.group(2)) if match.group(2) else low
        tokens.update(f"c{n}" for n in range(low, high + 1) if n in _CLASS_NUMBERS)
    return frozenset(tokens)


_cached_space_tokens = functools.cache(space_tokens)


def _match_space(value: str, site: Site) -> bool:
    if value in site.space.lower():
        return True
    tokens = _cached_space_tokens(site.space)
    if WILDCARD in tokens:
        return True
    wants = _SPACE_ALIASES.get(value, frozenset({value}))
    if not wants.isdisjoint(tokens):
        return True
    if "wormhole" in tokens and tokens.isdisjoint(_WH_SPECIFIC) and not wants.isdisjoint(_WH_KINDS):
        return True  # a bare "Wormhole" spawns in every class
    return "wormhole" in wants and not tokens.isdisjoint(_WH_KINDS)


# -- type -----------------------------------------------------------------------


def _match_type(value: str, site: Site) -> bool:
    haystacks = (type_label(site), site.category.replace("_", " "), site.scan_group, site.rating or "")
    return any(value in text.lower() for text in haystacks)


# -- danger ---------------------------------------------------------------------

_LABEL_LEVELS: dict[str, int] = {label.lower(): level for level, label in enumerate(db.DANGER_LABELS)}
_DANGER_OP = re.compile(r"^(<=|>=|<|>|=)?(.+)$")
_OPERATORS: dict[str, Callable[[int, int], bool]] = {
    "<=": lambda danger, level: danger <= level,
    ">=": lambda danger, level: danger >= level,
    "<": lambda danger, level: danger < level,
    ">": lambda danger, level: danger > level,
    "=": lambda danger, level: danger == level,
}


def _danger_level(token: str) -> int | None:
    """``"3"`` → 3, ``"medium"`` → 3, anything else → ``None``."""
    if token.isdecimal():
        return int(token)
    return _LABEL_LEVELS.get(token)


@functools.cache
def _danger_predicate(value: str) -> Callable[[int], bool] | None:
    """Compile a ``danger:`` value; ``None`` when it is not valid (matches nothing)."""
    if "-" in value:
        low_text, _, high_text = value.partition("-")
        low, high = _danger_level(low_text), _danger_level(high_text)
        if low is None or high is None:
            return None
        return lambda danger: low <= danger <= high
    match = _DANGER_OP.match(value)
    if match is None:
        return None
    operator = _OPERATORS[match.group(1) or "="]
    level = _danger_level(match.group(2))
    if level is None:
        return None
    return lambda danger: operator(danger, level)


def _match_danger(value: str, site: Site) -> bool:
    predicate = _danger_predicate(value)
    return predicate is not None and predicate(site.danger)


# -- plain substring fields -----------------------------------------------------


def _substring(attribute: str) -> Callable[[str, Site], bool]:
    def match(value: str, site: Site) -> bool:
        text: str | None = getattr(site, attribute)
        return text is not None and value in text.lower()

    return match


Matcher = Callable[[str, Site], bool]

FIELDS: dict[str, Matcher] = {
    "space": _match_space,
    "type": _match_type,
    "danger": _match_danger,
    "ship": _substring("min_ship"),
    "status": _substring("status"),
    "faction": _substring("faction"),
    "name": _substring("name"),
    "ewar": _substring("ewar"),
}
"""Field name → matcher ``(lower-cased value, site) -> bool``."""


# -- query ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FieldFilter:
    """One ``field:value`` term."""

    field: str
    """A key of :data:`FIELDS`."""
    value: str
    """Lower-cased value as typed after the colon."""
    negate: bool = False

    def matches(self, site: Site) -> bool:
        return FIELDS[self.field](self.value, site) != self.negate


@dataclass(frozen=True, slots=True)
class Query:
    """A parsed filter-box text: the plain fzf part plus the field filters."""

    plain: str
    """The plain terms re-joined with single spaces, for :func:`expo_catalog.fuzzy.rank`."""
    filters: tuple[FieldFilter, ...] = ()

    def matches(self, site: Site) -> bool:
        """``True`` when ``site`` passes every field filter (always for a query without any)."""
        return all(term.matches(site) for term in self.filters)

    def has_field(self, name: str) -> bool:
        """Whether any field term (negated or not) uses ``name``."""
        return any(term.field == name for term in self.filters)


def _parse_token(token: str) -> FieldFilter | None:
    """``!space:c3`` → :class:`FieldFilter`; ``None`` for anything that is not a field term."""
    negate = token.startswith("!")
    body = token[1:] if negate else token
    name, colon, value = body.partition(":")
    if not colon:
        return None
    name = name.lower()
    if name not in FIELDS:
        return None
    return FieldFilter(name, value.lower(), negate)


def parse_query(text: str) -> Query:
    """Split ``text`` into field terms and the remaining plain fzf query."""
    plain: list[str] = []
    filters: list[FieldFilter] = []
    for token in text.split():
        term = _parse_token(token)
        if term is None:
            plain.append(token)
        elif term.value:  # "space:" without a value is still being typed
            filters.append(term)
    return Query(" ".join(plain), tuple(filters))
