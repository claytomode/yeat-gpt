"""Yeat chat-voice helpers: slang dictionary, ad-libs, and title-style spelling.

Spelling rule (verified against his titles):
- Primary stylization is e -> ë on content words (alivë, monëy, lyfë).
- a/o/u/i diacritics (ä/ö/ü/ï) show up in branding sometimes, but far less often
  than ë; chat replies should prefer ë and only borrow other vowels when the
  mined title spelling already uses them.
- Never stylize function words (the, I, you, a, to, ...).
- At most two stylized words per reply.
"""

from __future__ import annotations

import re
from collections import Counter

from yeat_gpt.scrape.scope import FUNCTION_WORDS, fold_text

# Extra common English that should never land in the slang dictionary.
# Stored as fold_text() keys (apostrophes stripped), e.g. I'm -> im.
COMMON_ENGLISH = frozenset(
    """
    im dont cant wont its thats theres hes shes theyre were
    got get gettin getting all bitch fuck fucking shit love know knowin
    gonna wanna gotta aint never always still back when then
    come comein coming make made makein making take took see seen look
    lookin looking feel feelin feeling real really right left keep keepin
    keeping stay stayin staying run runnin running walk walkin walking
    talk talkin talking say sayin saying tell told call callin calling
    put puttin putting pull pullin pulling need needin needing want
    wantin wanting think thinkin thinking man boy girl baby night day
    time life rich poor high low big small new old good bad
    woo ooh huh nah off how now why who yes yet em bout
    every even said hey give them some pulled body lot ima
    lil fuckin diamonds
    """.split()
)

# Seed slang that must appear in the training dictionary even if mining is thin.
SEED_SLANG = (
    "twizzy",
    "tonka",
    "lyfe",
    "lyfestyle",
    "geek",
    "rage",
    "tun",
    "tunna",
    "luh",
    "frak",
    "rackz",
    "ion",
    "nvr",
    "dnt",
    "jus",
    "boutta",
    "trendy",
    "swerved",
    "cant",
    "ceo",
    "pockets",
    "notify",
    "hëavy",
    "monëy",
    "alivë",
    "lyfë",
)

SEED_ADLIBS = (
    "yeah",
    "yuh",
    "ayy",
    "what",
    "lets go",
    "tonka",
    "twizzy",
    "luh",
)

_VOWEL_STYLE = {
    "e": "ë",
    "a": "ä",
    "o": "ö",
    "u": "ü",
    "i": "ï",
}


def is_function_word(token: str) -> bool:
    folded = fold_text(token)
    compact = folded.replace(" ", "")
    return (
        folded in FUNCTION_WORDS
        or compact in FUNCTION_WORDS
        or folded in COMMON_ENGLISH
        or compact in COMMON_ENGLISH
    )


def stylize_content_word(word: str, *, vowel: str = "e") -> str | None:
    """Return a diacritic form for a content word, or None if it should stay plain.

    Default vowel is e->ë only. Other vowels are opt-in because Yeat titles use
    them rarely; do not invent ä/ö/ü/ï for ordinary slang like twizzy or tonka.
    """
    if not word or is_function_word(word):
        return None
    letters = re.findall(r"[A-Za-z]", word)
    if len(letters) < 3:
        return None
    vowel = vowel.lower()
    if vowel not in _VOWEL_STYLE:
        return None
    chars = list(word)
    indices = [i for i, ch in enumerate(chars) if ch.lower() == vowel]
    if not indices:
        return None
    idx = indices[-1]
    ch = chars[idx]
    styled = _VOWEL_STYLE[vowel]
    chars[idx] = styled.upper() if ch.isupper() else styled
    return "".join(chars)


def limit_stylized_words(text: str, *, max_words: int = 2) -> str:
    """Keep at most max_words diacritic tokens; strip extras back to ASCII fold."""
    from yeat_gpt.scrape.scope import fold_text as _fold

    count = 0
    out: list[str] = []
    for token in text.split():
        core = re.sub(r"^[^\w]+|[^\w]+$", "", token)
        if any(ord(c) > 127 for c in core):
            count += 1
            if count > max_words or is_function_word(core):
                # Reconstruct punctuation shell around folded core.
                folded = _fold(core)
                token = token.replace(core, folded, 1)
        out.append(token)
    return " ".join(out)


def _preferred_spellings() -> dict[str, str]:
    """Map folded plaintext -> preferred stylized form from seeds / dictionary."""
    preferred: dict[str, str] = {}

    def remember(word: str, *, invent_e: bool = False) -> None:
        word = str(word).strip()
        if not word or is_function_word(word):
            return
        folded = fold_text(word)
        if any(ord(c) > 127 for c in word):
            preferred[folded] = word.casefold()
            return
        if not invent_e or folded in preferred:
            return
        # Only invent ë for known brand words that contain e.
        styled = stylize_content_word(word, vowel="e")
        if styled and styled != word:
            preferred[folded] = styled.casefold()

    for word in SEED_SLANG:
        remember(word, invent_e=False)
    for word in ("lyfe", "alive", "money", "lyfestyle", "geek"):
        remember(word, invent_e=True)
    for word in ("lyfë", "alivë", "monëy", "lyfestylë", "gëek"):
        remember(word)
    try:
        import json

        from yeat_gpt.config import DICTIONARY_PATH

        if DICTIONARY_PATH.is_file():
            payload = json.loads(DICTIONARY_PATH.read_text(encoding="utf-8"))
            for tok in payload.get("stylized_title_tokens") or []:
                remember(str(tok))
            for tok in payload.get("slang") or []:
                tok_s = str(tok)
                if any(ord(c) > 127 for c in tok_s):
                    remember(tok_s)
    except Exception:
        pass
    return preferred


def apply_voice_spelling(text: str, *, max_stylized: int = 2) -> str:
    """Stylize at most two content words using mined/seed spellings only."""
    preferred = _preferred_spellings()
    words = text.split()
    stylized_at: list[int] = []
    for i, word in enumerate(words):
        core = re.sub(r"^[^\wëüöïäËÜÖÏÄ]+|[^\wëüöïäËÜÖÏÄ]+$", "", word)
        if not core or is_function_word(core):
            continue
        if any(ord(c) > 127 for c in core):
            stylized_at.append(i)
            continue
        if len(stylized_at) >= max_stylized:
            continue
        folded = fold_text(core)
        styled = preferred.get(folded)
        if not styled or fold_text(styled) != folded:
            continue
        # Preserve original capitalization shell loosely.
        if core[0].isupper():
            styled = styled[0].upper() + styled[1:]
        words[i] = word.replace(core, styled, 1)
        stylized_at.append(i)
    return limit_stylized_words(" ".join(words), max_words=max_stylized)


def mine_dictionary(songs: list[dict]) -> dict:
    """Build slang / ad-lib / title-spelling dictionary from the cleaned catalog."""
    title_spellings: Counter = Counter()
    content_words: Counter = Counter()
    adlib_hits: Counter = Counter()
    repeated_phrases: Counter = Counter()

    adlib_set = {a.casefold() for a in SEED_ADLIBS}
    for song in songs:
        title = str(song.get("title") or "")
        for tok in re.findall(r"[A-Za-z0-9ëüöïäËÜÖÏÄ']+", title):
            if len(tok) > 2 and not is_function_word(tok):
                title_spellings[tok] += 1
        lines = [ln.strip() for ln in str(song.get("text") or "").splitlines() if ln.strip()]
        for line in lines:
            low = line.casefold()
            for adlib in adlib_set:
                if re.search(rf"\b{re.escape(adlib)}\b", low):
                    adlib_hits[adlib] += 1
            tokens = re.findall(r"[a-z0-9ëüöïä']{3,}", low)
            for tok in tokens:
                if not is_function_word(tok):
                    content_words[tok] += 1
            # Short repeated hooks / clauses
            if 3 <= len(line.split()) <= 8:
                repeated_phrases[line] += 1

    slang = []
    seen = set()
    for word in SEED_SLANG:
        key = fold_text(word)
        if key not in seen:
            slang.append(word)
            seen.add(key)
    for word, count in content_words.most_common(300):
        if count < 4:
            break
        key = fold_text(word)
        if key in seen or is_function_word(word):
            continue
        slang.append(word)
        seen.add(key)
        if len(slang) >= 160:
            break

    stylized_titles = [
        tok for tok, _ in title_spellings.most_common(80) if any(ord(c) > 127 for c in tok)
    ]
    phrases = [p for p, c in repeated_phrases.most_common(80) if c >= 2]

    return {
        "spelling_rules": {
            "primary": "Mark e as ë on content words (alivë, monëy). Prefer the last e.",
            "other_vowels": (
                "a/o/u/i diacritics appear in some titles but are rarer; "
                "prefer ë in chat unless a mined title spelling already uses another vowel."
            ),
            "never": sorted(FUNCTION_WORDS),
            "max_stylized_words_per_reply": 2,
        },
        "slang": slang,
        "adlibs": [w for w, _ in adlib_hits.most_common(40)] or list(SEED_ADLIBS),
        "title_spellings": title_spellings.most_common(60),
        "stylized_title_tokens": stylized_titles[:40],
        "repeated_phrases": phrases[:60],
    }
