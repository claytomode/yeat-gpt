"""Style lexicon and phrase bank mining — preserve Unicode."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from yeat_gpt.clean.voice import mine_dictionary

GENERIC_STOP = frozenset(
    "i me my we you the a an and or but in on at to for of is it that this with from".split()
)

THEME_KEYWORDS: dict[str, list[str]] = {
    "vehicles": ["tonka", "bentley", "jeep", "truck", "car", "drive"],
    "drugs": ["perc", "xan", "x ", "lean", "perk", "drug", "pill"],
    "money": ["money", "cash", "rich", "bank", "paid", "rackz", "monëy"],
    "flex": ["diamond", "ice", "watch", "chain", "ring", "eli", "twizzy"],
    "lyfe": ["lyfe", "lyfë", "alive", "alivë", "geek", "rage", "ceo"],
}


def has_diacritic(s: str) -> bool:
    return any(ord(c) > 127 for c in s)


def mine_style_lexicon(titles: list[str], lyric_tokens: Counter) -> dict:
    title_tokens: Counter = Counter()
    for title in titles:
        for tok in re.findall(r"[a-zA-Z0-9ëüöïä]+", title):
            if len(tok) > 2 and tok.lower() not in GENERIC_STOP:
                title_tokens[tok] += 1
    stylized = [t for t, _ in title_tokens.most_common(80) if has_diacritic(t) or t.isupper()]
    frequent = [
        token
        for token, count in lyric_tokens.most_common(200)
        if count >= 8 and token.lower() not in GENERIC_STOP
    ]
    return {
        "title_tokens": title_tokens.most_common(50),
        "stylized": stylized[:40],
        "frequent": frequent[:80],
    }


def mine_phrase_bank(songs: list[dict]) -> dict:
    """Build phrase bank with example bars per term."""
    term_lines: dict[str, list[dict]] = {}
    for song in songs:
        text = song.get("text", "")
        title = song.get("title", "")
        for line in text.splitlines():
            line = line.strip()
            if len(line) < 12:
                continue
            low = line.lower()
            for theme, keywords in THEME_KEYWORDS.items():
                for kw in keywords:
                    if kw.strip() in low:
                        term = kw.strip()
                        term_lines.setdefault(term, [])
                        if len(term_lines[term]) < 5:
                            term_lines[term].append(
                                {"line": line, "song": title, "theme": theme}
                            )
    return {"terms": {k: v for k, v in sorted(term_lines.items())}}


def save_lexicons(
    songs: list[dict],
    out_style: Path,
    out_phrase: Path,
    out_dictionary: Path | None = None,
) -> None:
    titles = [s["title"] for s in songs]
    token_counter: Counter = Counter()
    for song in songs:
        for tok in re.findall(r"[a-zA-Z0-9ëüöïä]{3,}", song.get("text", "").lower()):
            if tok not in GENERIC_STOP:
                token_counter[tok] += 1
    style = mine_style_lexicon(titles, token_counter)
    phrase = mine_phrase_bank(songs)
    dictionary = mine_dictionary(songs)
    style["dictionary_slang_preview"] = dictionary["slang"][:40]
    style["spelling_rules"] = dictionary["spelling_rules"]
    out_style.parent.mkdir(parents=True, exist_ok=True)
    out_style.write_text(json.dumps(style, indent=2, ensure_ascii=False), encoding="utf-8")
    out_phrase.write_text(json.dumps(phrase, indent=2, ensure_ascii=False), encoding="utf-8")
    if out_dictionary is not None:
        out_dictionary.write_text(
            json.dumps(dictionary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
