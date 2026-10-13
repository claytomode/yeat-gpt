"""Ad-lib detection and line filtering."""

from __future__ import annotations

import re

ADLIB_TOKENS = frozenset(
    {
        "yeah",
        "yea",
        "yuh",
        "yup",
        "what",
        "nah",
        "ha",
        "huh",
        "ayy",
        "aye",
        "oh",
        "woo",
        "woah",
        "skrr",
        "buh",
        "brah",
        "brazy",
        "lets",
        "let's",
        "go",
    }
)

_TOKEN_ALT = "|".join(re.escape(token) for token in sorted(ADLIB_TOKENS, key=len, reverse=True))
ADLIB_ONLY_PATTERN = re.compile(
    rf"^[\s,.\-!?'\"]*({_TOKEN_ALT})[\s,.\-!?'\"]*$",
    re.IGNORECASE,
)


def tokenize_line(line: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9ëüöïáé]+", line.lower())


def adlib_ratio(line: str) -> float:
    tokens = tokenize_line(line)
    if not tokens:
        return 1.0
    adlib_count = sum(1 for token in tokens if token in ADLIB_TOKENS)
    return adlib_count / len(tokens)


def is_adlib_only_line(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) <= 3:
        return True
    if ADLIB_ONLY_PATTERN.match(stripped):
        return True
    return adlib_ratio(stripped) >= 0.85 and len(tokenize_line(stripped)) <= 4


def strip_inline_adlibs(line: str) -> str:
    """Remove standalone ad-lib tokens; keep coded nouns like tonka, percs."""
    tokens = line.split()
    kept: list[str] = []
    for tok in tokens:
        core = re.sub(r"[^\wëüöï]", "", tok.lower())
        if core in ADLIB_TOKENS and len(tokens) > 2:
            continue
        kept.append(tok)
    return " ".join(kept).strip()


def filter_lines(lines: list[str], *, for_verse: bool = True) -> tuple[list[str], dict[str, int]]:
    """Filter ad-lib lines; optionally strip inline adlibs for verse training."""
    stats = {"input": len(lines), "dropped_adlib": 0, "deduped": 0}
    out: list[str] = []
    prev: str | None = None
    for line in lines:
        if is_adlib_only_line(line):
            stats["dropped_adlib"] += 1
            continue
        cleaned = strip_inline_adlibs(line) if for_verse else line.strip()
        if not cleaned:
            stats["dropped_adlib"] += 1
            continue
        if prev and cleaned.lower() == prev.lower() and len(cleaned) < 40:
            stats["deduped"] += 1
            continue
        out.append(cleaned)
        prev = cleaned
    stats["output"] = len(out)
    return out, stats


def collapse_consecutive_duplicates(lines: list[str]) -> list[str]:
    if not lines:
        return []
    out = [lines[0]]
    for line in lines[1:]:
        if line.lower() != out[-1].lower():
            out.append(line)
    return out
