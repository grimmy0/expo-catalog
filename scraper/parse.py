"""Parse cached EVE University wikitext pages into structured site records.

Handles the templates the wiki uses for exploration sites:

* ``{{CMBSiteInfo|name=|type=|rating=|location=|ship limit=|faction=|...}}``
* ``{{Infobox gas nebula|type=|subtype=|location=|is guarded=|...}}``
* ``{{NPCTableHead|<wave>}}`` followed by ``{{NPCTableRow|<Class>|<count>|<name>|k=v...}}``
* ``{{npcwh|<code>|<N>x}}`` Sleeper rows (codes resolved via ``data/npcwh_codes.json``)
* ``{{Past content}}``, ``{{Update|..}}``, ``{{Stub}}``, ``{{Merge|..}}`` status flags

Besides the git-ignored wiki cache in ``data/raw/``, parsing reads two tracked,
hand-maintained inputs: ``data/npcwh_codes.json`` (the Sleeper NPC code table behind
``{{npcwh}}`` rows) and ``data/Template_Whisk.wiki`` (blue-loot values behind ``{{whisk}}``).
Both are required; a missing file raises instead of silently degrading the output.

Run ``uv run python -m scraper.parse`` to write ``data/parsed_sites.json``.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from scraper.wiki import RAW_DIR, WIKI_DIR, load_category_index

DATA_DIR = RAW_DIR.parent
PARSED_FILE = DATA_DIR / "parsed_sites.json"
NPCWH_FILE = DATA_DIR / "npcwh_codes.json"
WHISK_TEMPLATE = DATA_DIR / "Template_Whisk.wiki"

HOSTILE_CLASSES = {
    "frigate": "frigate",
    "mining frigate": "frigate",
    "destroyer": "destroyer",
    "cruiser": "cruiser",
    "storyline mission cruiser": "cruiser",
    "battlecruiser": "battlecruiser",
    "battleship": "battleship",
    "carrier": "carrier",
    "supercarrier": "supercarrier",
    "dreadnought": "dreadnought",
    "titan": "titan",
    "sentry": "sentry",
    "tower": "sentry",
    "drone": "drone",
    "fighter": "fighter",
    "hauler": "industrial",
    "industrial": "industrial",
    "freighter": "industrial",
    "barge": "industrial",
}
TIER_PREFIXES = ("elite", "commander", "overseer", "officer")
SIDE_PREFIXES = ("neutral", "friendly")

CLASS_ORDER = (
    "frigate",
    "destroyer",
    "cruiser",
    "battlecruiser",
    "battleship",
    "dreadnought",
    "carrier",
    "supercarrier",
    "titan",
    "drone",
    "fighter",
    "sentry",
    "industrial",
)

# Templates that carry no prose and should be dropped before looking for a description.
LEADING_TEMPLATES = (
    "CMBSiteInfo",
    "Infobox gas nebula",
    "NPCTableCSS",
    "Update",
    "Past content",
    "Stub",
    "Merge",
    "cleanup",
    "hatnote",
    "main",
    "whcobox",
    "Exploration links",
    "Wormhole Links",
    "HomefrontOperationsLinks",
    "Industry Links",
    "CMBSite",
    "MessageBox",
    "Note box",
    "note box",
    "Note",
    "expansion past",
)


@dataclass
class NpcRow:
    wave: str
    ship_class: str  # normalised: frigate, destroyer, ... sentry, drone, industrial
    raw_class: str
    count_min: int | None
    count_max: int | None
    name: str
    tier: str | None = None  # elite / commander / overseer / officer
    hostile: bool = True
    ewar: list[str] = field(default_factory=list)
    trigger: str | None = None
    note: str | None = None
    section: str | None = None  # nearest preceding == heading == (room / pocket)


@dataclass
class ParsedPage:
    title: str
    file: str
    categories: list[str]
    flags: dict[str, str | bool]
    infobox_kind: str | None
    infobox: dict[str, str]
    npc_rows: list[NpcRow]
    description: str
    escalations: list[str]
    blue_loot_isk: int | None
    merge_target: str | None


# --------------------------------------------------------------------------- helpers
def split_top_level(text: str, sep: str = "|") -> list[str]:
    """Split on ``sep`` ignoring separators nested in {{ }} or [[ ]]."""
    parts: list[str] = []
    depth_t = depth_l = 0
    buf: list[str] = []
    i = 0
    while i < len(text):
        two = text[i : i + 2]
        if two == "{{":
            depth_t += 1
            buf.append(two)
            i += 2
            continue
        if two == "}}" and depth_t:
            depth_t -= 1
            buf.append(two)
            i += 2
            continue
        if two == "[[":
            depth_l += 1
            buf.append(two)
            i += 2
            continue
        if two == "]]" and depth_l:
            depth_l -= 1
            buf.append(two)
            i += 2
            continue
        ch = text[i]
        if ch == sep and not depth_t and not depth_l:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def find_templates(text: str, name: str) -> list[str]:
    """Return the inner text of every ``{{name ...}}`` template (case-insensitive name).

    The inner text starts right after the template name (so it begins with ``|`` when the
    template has arguments) and excludes the closing braces.
    """
    out: list[str] = []
    pattern = re.compile(r"\{\{\s*" + re.escape(name) + r"\s*(?=[|}\n])", re.I)
    for m in pattern.finditer(text):
        start = m.end()
        depth = 1
        i = start
        while i < len(text) and depth:
            two = text[i : i + 2]
            if two == "{{":
                depth += 1
                i += 2
            elif two == "}}":
                depth -= 1
                i += 2
            else:
                i += 1
        out.append(text[start : i - 2] if depth == 0 else text[start:])
    return out


def remove_templates(text: str, name: str) -> str:
    """Remove every ``{{name ...}}`` template (with its braces) from ``text``."""
    pattern = re.compile(r"\{\{\s*" + re.escape(name) + r"\s*(?=[|}\n])", re.I)
    while True:
        m = pattern.search(text)
        if not m:
            return text
        depth = 1
        i = m.end()
        while i < len(text) and depth:
            two = text[i : i + 2]
            if two == "{{":
                depth += 1
                i += 2
            elif two == "}}":
                depth -= 1
                i += 2
            else:
                i += 1
        text = text[: m.start()] + text[i:]


def strip_markup(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<ref[^>]*/>", "", text)
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", text, flags=re.I)
    text = re.sub(r"\{\{\s*co\|[^|}]*\|([^}]*)\}\}", r"\1", text, flags=re.I)
    text = re.sub(r"\{\{\s*(?:sk|m3|verify|clear|NPCTableCSS|icon)\b[^}]*\}\}", "", text, flags=re.I)
    text = re.sub(
        r"\{\{\s*Damagetype\s*\|([^}]*)\}\}",
        lambda m: "/".join(x.strip() for x in m.group(1).split("|") if x.strip()),
        text,
        flags=re.I,
    )
    # [[target|label]] -> label ; [[target]] -> target
    text = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\]", "", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ")
    return re.sub(r"[ \t]+", " ", text).strip()


def parse_kv(inner: str) -> dict[str, str]:
    """Parse ``|key=value`` pairs from template inner text (leading positional parts skipped)."""
    out: dict[str, str] = {}
    for part in split_top_level(inner)[1:]:
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        key = key.strip().lower()
        value = strip_markup(value).strip()
        if key and value:
            out[key] = value
    return out


COUNT_RE = re.compile(r"\d+")


def parse_count(raw: str) -> tuple[int | None, int | None]:
    """Parse NPC counts like ``1-2``, ``0-1``, ``15``, ``2–3``, ``3x``, ``2-3x``, ``4+``, ``?``."""
    raw = raw.replace("–", "-").replace("—", "-").lower()
    raw = re.sub(r"\(.*?\)", "", raw)
    nums = [int(n) for n in COUNT_RE.findall(raw)]
    if not nums:
        return None, None
    if len(nums) >= 2 and ("-" in raw or " to " in raw or "/" in raw):
        return min(nums[0], nums[1]), max(nums[0], nums[1])
    if "+" in raw:
        return nums[0], None
    return nums[0], nums[0]


def normalise_class(raw: str) -> tuple[str | None, str | None, bool]:
    """Return (normalised class or None if not a ship, tier, hostile)."""
    raw = raw.strip().lower().split("/")[0]  # "Frigate/destroyer" -> frigate
    words = raw.replace("-", " ").split()
    hostile = True
    tier = None
    while words and words[0] in SIDE_PREFIXES:
        hostile = False
        words.pop(0)
    while words and words[0] in TIER_PREFIXES:
        tier = words.pop(0)
    key = " ".join(words)
    if key in HOSTILE_CLASSES:
        return HOSTILE_CLASSES[key], tier, hostile
    key_singular = key.rstrip("s")
    if key_singular in HOSTILE_CLASSES:
        return HOSTILE_CLASSES[key_singular], tier, hostile
    return None, tier, hostile


def _row_from_parts(wave: str, parts: list[str], section: str | None = None) -> NpcRow | None:
    positional: list[str] = []
    named_parts: list[str] = []
    for p in parts[1:]:
        # A positional argument never contains '=' outside of nested links/templates.
        head = re.split(r"\{\{|\[\[", p, maxsplit=1)[0]
        if "=" in head:
            named_parts.append(p)
        else:
            positional.append(p)
    if len(positional) < 2:
        return None
    named = parse_kv("|" + "|".join(named_parts)) if named_parts else {}
    raw_class = strip_markup(positional[0])
    ship_class, tier, hostile = normalise_class(raw_class)
    if ship_class is None:
        return None  # structures, gates, containers, asteroids, hackables
    cmin, cmax = parse_count(positional[1])
    name = strip_markup(positional[2]) if len(positional) > 2 else ""
    ewar = [v for k, v in named.items() if k.startswith("ewar")]
    point = named.get("point")
    if point:
        ewar.append("point" if point.lower() in ("yes", "y", "true") else point)
    return NpcRow(
        wave=wave,
        ship_class=ship_class,
        raw_class=raw_class,
        count_min=cmin,
        count_max=cmax,
        name=name,
        tier=tier,
        hostile=hostile,
        ewar=ewar,
        trigger=named.get("trigger"),
        note=named.get("note"),
        section=section,
    )


HEADING_RE = re.compile(r"^(=+)\s*(.+?)\s*\1\s*$", re.M)


def parse_npc_tables(text: str) -> list[NpcRow]:
    rows: list[NpcRow] = []
    head_re = re.compile(r"\{\{\s*NPCTableHead\s*(?:\|([^}]*))?\}\}", re.I)
    headings = [(m.start(), strip_markup(m.group(2))) for m in HEADING_RE.finditer(text)]
    heads = list(head_re.finditer(text))
    for idx, head in enumerate(heads):
        wave = strip_markup(head.group(1) or "") or f"Table {idx + 1}"
        section = None
        for pos, title in headings:
            if pos < head.start():
                section = title
            else:
                break
        end = heads[idx + 1].start() if idx + 1 < len(heads) else len(text)
        body = text[head.end() : end]
        close = body.find("\n|}")
        if close != -1:
            body = body[:close]
        for inner in find_templates(body, "NPCTableRow"):
            parts = [p.strip() for p in split_top_level(inner)]
            try:
                row = _row_from_parts(wave, parts, section)
            except Exception as exc:  # pragma: no cover - defensive
                print(f"  warning: bad NPCTableRow {inner[:60]!r}: {exc}", file=sys.stderr)
                continue
            if row is not None:
                rows.append(row)
    return rows


def _require(path: Path, what: str) -> Path:
    if not path.exists():
        raise FileNotFoundError(f"{what} not found at {path}; it is a tracked input (restore it from git)")
    return path


def load_npcwh_codes() -> dict[str, dict]:
    """Sleeper NPC code table used to resolve ``{{npcwh}}`` rows (required)."""
    return json.loads(_require(NPCWH_FILE, "Sleeper NPC code table").read_text(encoding="utf-8"))


def parse_sleeper_rows(text: str, codes: dict[str, dict]) -> list[NpcRow]:
    rows: list[NpcRow] = []
    wave = "Wave 1"
    for inner in find_templates(text, "npcwh"):
        parts = [p.strip() for p in split_top_level(inner)]
        if len(parts) < 2:
            continue
        code = parts[1].lower()
        if code in ("start", "start2", "end"):
            continue
        if code == "wave":
            label = strip_markup(parts[2]) if len(parts) > 2 else ""
            wave = label or wave
            continue
        info = codes.get(code) or codes.get(parts[1])
        if not info:
            continue
        count_raw = parts[2] if len(parts) > 2 and parts[2] else "1"
        cmin, cmax = parse_count(count_raw)
        cls = info["class"]
        ship_class = "sentry" if cls == "tower" else cls
        rows.append(
            NpcRow(
                wave=wave,
                ship_class=ship_class,
                raw_class=cls,
                count_min=cmin,
                count_max=cmax,
                name=info["name"],
                ewar=list(info.get("ewar", [])),
                trigger="trigger" if any("trigger" in p.lower() for p in parts[3:]) else None,
            )
        )
    return rows


def first_paragraph(text: str) -> str:
    body = text
    for name in LEADING_TEMPLATES:
        body = remove_templates(body, name)
    # Drop any remaining simple (non-nested) templates.
    body = re.sub(r"\{\{[^{}]*\}\}", "", body)
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith(("{", "|", "=", "[[Category", "<!--", "*", "#", "!", "}", "----")):
            continue
        clean = strip_markup(line)
        if len(clean) > 40:
            return clean[:600]
    return ""


def parse_escalations(text: str) -> list[str]:
    links: list[str] = []
    section = re.search(r"==+\s*Escalations?\s*==+(.*?)(?:\n==|\Z)", text, re.S | re.I)
    if section:
        links += re.findall(r"\[\[([^\]|#]+)", section.group(1))
    for m in re.finditer(r"escalat\w*\s+(?:in)?to\s+(?:the\s+)?(?:\[\[[^\]]*\]\]\s*)*\[\[([^\]|#]+)", text, re.I):
        links.append(m.group(1))
    seen: list[str] = []
    for link in links:
        link = link.strip()
        if link and link not in seen and not link.lower().startswith(("file:", "image:", "category:")):
            seen.append(link)
    return seen


def parse_blue_loot(text: str, whisk: dict[str, int]) -> int | None:
    for inner in find_templates(text, "whisk"):
        parts = split_top_level(inner)
        code = parts[1].strip().lower() if len(parts) > 1 else ""
        if code in whisk:
            return whisk[code]
    m = re.search(r"([\d,]{6,})\s*(?:ISK\s*)?(?:in|of|for)?\s*blue\s*loot", text, re.I)
    if m:
        return int(m.group(1).replace(",", ""))
    m = re.search(r"blue\s*loot[^\d]{0,20}([\d,]{6,})", text, re.I)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def load_whisk() -> dict[str, int]:
    """Map whisk short codes to blue-loot ISK from the tracked ``Template:Whisk`` copy (required)."""
    text = _require(WHISK_TEMPLATE, "Template:Whisk copy").read_text(encoding="utf-8")
    out: dict[str, int] = {}
    pattern = re.compile(r"\|\s*([^|=\n]+?)\s*\|\s*([a-z0-9]+)\s*=\s*\*?\s*([\d,]+)")
    for m in pattern.finditer(text):
        out[m.group(2).lower()] = int(m.group(3).replace(",", ""))
    return out


def parse_flags(text: str) -> dict[str, str | bool]:
    flags: dict[str, str | bool] = {}
    for name, key in (
        ("Past content", "past_content"),
        ("Update", "needs_update"),
        ("Stub", "stub"),
        ("cleanup", "cleanup"),
        ("expansion past", "expansion_past"),
    ):
        found = find_templates(text, name)
        if found:
            parts = split_top_level(found[0])
            note = strip_markup(parts[1]) if len(parts) > 1 else ""
            flags[key] = note or True
    return flags


def parse_page(
    path: Path,
    category_index: dict[str, set[str]],
    codes: dict[str, dict],
    whisk: dict[str, int],
) -> ParsedPage:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"<!-- TITLE: (.*?) -->\n", text)
    title = m.group(1) if m else path.stem
    if m:
        text = text[m.end() :]
    categories = set(re.findall(r"\[\[\s*Category:\s*([^\]|]+)", text)) | category_index.get(title, set())
    categories_clean = sorted({c.strip().replace("_", " ") for c in categories if c.strip()})

    infobox_kind: str | None = None
    infobox: dict[str, str] = {}
    for kind in ("CMBSiteInfo", "Infobox gas nebula"):
        found = find_templates(text, kind)
        if found:
            infobox_kind = kind
            infobox = parse_kv(found[0])
            break

    merge_target = None
    merge = find_templates(text, "Merge")
    if merge:
        kv = parse_kv(merge[0])
        parts = split_top_level(merge[0])
        merge_target = kv.get("target") or (strip_markup(parts[1]) if len(parts) > 1 else None)
        if merge_target and merge_target.strip().lower() == title.strip().lower():
            merge_target = None  # this page IS the merge target

    npc_rows = parse_npc_tables(text) + parse_sleeper_rows(text, codes)
    return ParsedPage(
        title=title,
        file=path.name,
        categories=categories_clean,
        flags=parse_flags(text),
        infobox_kind=infobox_kind,
        infobox=infobox,
        npc_rows=npc_rows,
        description=first_paragraph(text),
        escalations=parse_escalations(text),
        blue_loot_isk=parse_blue_loot(text, whisk),
        merge_target=merge_target,
    )


def parse_all(wiki_dir: Path = WIKI_DIR) -> list[ParsedPage]:
    category_index = load_category_index()
    codes = load_npcwh_codes()
    whisk = load_whisk()
    pages: list[ParsedPage] = []
    for path in sorted(wiki_dir.glob("*.wiki")):
        try:
            pages.append(parse_page(path, category_index, codes, whisk))
        except Exception as exc:  # never let one odd page kill the run
            print(f"  warning: failed to parse {path.name}: {exc}", file=sys.stderr)
    return pages


def main() -> None:
    pages = parse_all()
    PARSED_FILE.write_text(json.dumps([asdict(p) for p in pages], indent=1, ensure_ascii=False), encoding="utf-8")
    with_rows = sum(1 for p in pages if p.npc_rows)
    with_box = sum(1 for p in pages if p.infobox)
    neither = sum(1 for p in pages if not p.npc_rows and not p.infobox)
    print(f"parsed {len(pages)} pages -> {PARSED_FILE.relative_to(RAW_DIR.parent.parent)}")
    print(
        f"  with infobox: {with_box}, with NPC rows: {with_rows}, neither: {neither}, "
        f"past content: {sum(1 for p in pages if p.flags.get('past_content'))}"
    )


if __name__ == "__main__":
    main()
