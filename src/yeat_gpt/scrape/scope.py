"""Training corpus scope: official albums through Dangerous Summer, plus curated leaks.

Anything newer than Dangerous Summer, remixes, live/paused cuts, and guest features
are out of scope. Early mixtape deep cuts are out unless listed under POPULAR_LEAKS.
"""

from __future__ import annotations

import re
import unicodedata

# Canonical album keys used in catalog metadata.
OFFICIAL_ALBUMS: dict[str, dict] = {
    "up_2_me": {
        "label": "Up 2 Me",
        "aliases": ("up 2 me", "up 2 më", "up 2 mе"),
        "tracks": (
            "Cmon",
            "Morning mudd",
            "Got rich",
            "Lët ya know",
            "Stayëd tha same",
            "Gët Busy",
            "Rokstar",
            "Trëndy Way",
            "Swërved It",
            "Ya Ya",
            "U could tëll",
            "Factz",
            "Bak on ëm",
            "Hëy",
            "Turban",
            "Twizzy Rich",
            "Told ya",
            "Monëy so big",
            "Dëserve it",
            "Kant changë",
            "Callin më",
            "Lying 4 fun",
        ),
    },
    "2_alive": {
        "label": "2 Alivë",
        "aliases": ("2 alive", "2 alivë", "2 alivë (geëk pack)", "2 alive (geek pack)"),
        "tracks": (
            "Poppin",
            "Rëal six",
            "Nvr again",
            "Luh gëek",
            "Doublë",
            "On tha linë",
            "Jus bëtter",
            "Jump",
            "Dnt lië",
            "Rollin",
            "Taliban",
            "Call më",
            "Kant dië",
            "Smooktobër",
            "Still countin",
            # Geëk Pack solo cuts (official deluxe)
            "Kant rëlax",
            "No commënt",
            "3G",
            "Nëw turban",
            "Hatër",
            "Way back",
            "Dub",
        ),
    },
    "lyfe": {
        "label": "Lyfë",
        "aliases": ("lyfe", "lyfë"),
        "tracks": (
            "Up off X",
            "Out thë way",
            "Wat it feel lykë",
            "Got it all",
            "Can't stop it",
            "Krank",
            "Talk",
            "Comë on",
            "Systëm",
            "Holy 1",
            "Killin ëm",
        ),
    },
    "afterlyfe": {
        "label": "AftërLyfe",
        "aliases": ("afterlyfe", "aftërlyfe", "aftër lyfe"),
        "tracks": (
            "No morë talk",
            "Bëttr 0ff",
            "Rav3 p4rty",
            "Nun id change",
            "Woa...!",
            "Now",
            "Slamm",
            "7 nightz",
            "Mëan feen",
            "How it go",
            "Sum 2 do",
            "Back up",
            "Split",
            "Bad bënd/DëMON",
            "Hëavyweight",
            "Watch",
            "Shhhh",
            "Back homë",
            "Type monëy",
            "Dëmon tied",
            "Mysëlf",
        ),
    },
    "2093": {
        "label": "2093",
        "aliases": ("2093", "2093 (p2)", "2093 (p3)"),
        "tracks": (
            "Psycho CEO",
            "Power Trip",
            "Breathe",
            "Morë",
            "Bought The Earth",
            "Nothing Changë",
            "U Should Know",
            "ILUV",
            "Tell më",
            "Shade",
            "Keep Pushin",
            "Riot & Set it off",
            "Team ceo",
            "2093",
            "Familia",
            "Mr. Inbetweenit",
            "Psychocainë",
            "Run Thëy Mouth",
            "If We Being Rëal",
            "1093",
        ),
    },
    "lyfestyle": {
        "label": "Lyfestyle",
        "aliases": ("lyfestyle", "lyfëstyle", "lyfestylë"),
        "tracks": (
            "GEEK TIMË",
            "STFU",
            "THEY TELL MË",
            "HEARD OF MË",
            "SPEEDBALL",
            "U DON'T KNOW LYFE",
            "ORCHESTRATË",
            "THE COSTËS",
            "GONE 4 A MIN",
            "FOREVER AGAIN",
            "ON 1",
            "FLYTROOP",
            "ELIMINATË",
            "LYING 5 FUN",
            "SO WHAT",
            "GOD TALKIN SHHH",
            "LYFE PARTY",
            "FATË",
        ),
    },
    "dangerous_summer": {
        "label": "Dangerous Summer",
        "aliases": ("dangerous summer",),
        "tracks": (
            "Put It Ong",
            "Loco",
            "Loose Leaf",
            "Come n Go",
            "[ADL Is Coming]",
            "IM YEAT",
            "Growing Pains",
        ),
    },
}

# Real, widely known early/leak cuts only — not a dump of every unreleased file.
POPULAR_LEAKS: dict[str, dict] = {
    "sorry_bout_that": {
        "label": "Popular leak / early",
        "search_titles": ("Sorry Bout That", "Sorry bout that"),
        "album_hints": ("4l", "sorry bout that", "yeat"),
    },
    "count_up": {
        "label": "Popular leak / early",
        "search_titles": ("Count Up", "Countup"),
        "album_hints": ("4l", "alive", "alivë", "yeat"),
    },
    "tonka": {
        "label": "Popular leak / early",
        "search_titles": ("Tonka", "Big tonka"),
        "album_hints": ("4l", "alive", "alivë", "2 alivë", "geek", "yeat"),
    },
}

# Guest vocal features we drop even when the song sits on an official album.
FEATURE_MARKERS = (
    "feat.",
    "feat ",
    "(feat",
    "ft.",
    "ft ",
    "(ft",
    " featuring ",
    "(with ",
)
FEATURE_ARTISTS = (
    "young thug",
    "gunna",
    "lil uzi",
    "lil wayne",
    "future",
    "ken carson",
    "septembersrich",
    "lancey",
    "kodak",
    "summrs",
    "don toliver",
    "lil durk",
    "ngeeyl",
    "sahbabii",
    "fka twigs",
    "fka",
    "yung kayo",
)

DROP_TITLE_MARKERS = (
    "remix",
    "live",
    "paused",
    "sped up",
    "slowed",
    "nightcore",
    "instrumental",
    "acapella",
    "a cappella",
    "clean",
    "radio edit",
    "pmedia",
    "[v1]",
    "[v2]",
    "[v3]",
    "[v4]",
    "[v5]",
    "sessions",
)

# Anything that clearly belongs after Dangerous Summer / ADL rollout.
NEWER_ALBUM_MARKERS = (
    "a dangerous lyfe",
    "a dangerous lyfë",
    "adl ",
    " on nothing",
    "on nothing",
)

FUNCTION_WORDS = frozenset(
    """
    a an the i you he she we they me my your his her our their it its
    is am are was were be been being to for of in on at by with from
    and or but if so as than then that this these those what who whom
    not no yes do does did done have has had will would can could should
    just like up out yeah yea yuh
    """.split()
)

_DIACRITIC_FOLD = str.maketrans(
    {
        "ë": "e",
        "Ë": "E",
        "ä": "a",
        "Ä": "A",
        "ö": "o",
        "Ö": "O",
        "ü": "u",
        "Ü": "U",
        "ï": "i",
        "Ï": "I",
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
    }
)


def fold_text(text: str) -> str:
    """Lowercase ASCII-ish fold for matching titles and albums."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.translate(_DIACRITIC_FOLD)
    text = text.casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def is_dropped_title(title: str) -> bool:
    low = f" {fold_text(title)} "
    raw = (title or "").casefold()
    if any(marker in raw for marker in DROP_TITLE_MARKERS):
        return True
    if any(marker in raw for marker in FEATURE_MARKERS):
        return True
    if any(f" with {artist}" in raw for artist in FEATURE_ARTISTS):
        return True
    if " remix" in low or low.endswith(" remix"):
        return True
    return False


def is_newer_project(album: str, title: str = "") -> bool:
    blob = f"{album} {title}".casefold()
    return any(marker in blob for marker in NEWER_ALBUM_MARKERS)


def match_official_album(album_name: str) -> str | None:
    folded = fold_text(album_name)
    if not folded:
        return None
    for key, meta in OFFICIAL_ALBUMS.items():
        for alias in meta["aliases"]:
            alias_f = fold_text(alias)
            if folded == alias_f or alias_f in folded or folded in alias_f:
                return key
    return None


def track_matches(wanted: str, candidate: str) -> bool:
    a = fold_text(wanted)
    b = fold_text(candidate)
    if not a or not b:
        return False
    if a == b:
        return True
    # Allow minor suffix noise like "song" pages without changing the core title.
    if a in b and abs(len(a) - len(b)) <= 4:
        return True
    return False


def wanted_track_queries() -> list[dict]:
    """Flatten official + leak search jobs for the LRCLIB scraper."""
    jobs: list[dict] = []
    for album_key, meta in OFFICIAL_ALBUMS.items():
        for title in meta["tracks"]:
            if is_dropped_title(title):
                continue
            jobs.append(
                {
                    "kind": "official",
                    "album_key": album_key,
                    "album_label": meta["label"],
                    "title": title,
                }
            )
    for leak_key, meta in POPULAR_LEAKS.items():
        for title in meta["search_titles"]:
            jobs.append(
                {
                    "kind": "leak",
                    "album_key": leak_key,
                    "album_label": meta["label"],
                    "title": title,
                    "album_hints": meta.get("album_hints", ()),
                }
            )
    return jobs


def score_candidate(job: dict, record: dict) -> int:
    """Higher is better. Negative means reject."""
    artist = str(record.get("artistName") or "")
    title = str(record.get("trackName") or record.get("name") or "")
    album = str(record.get("albumName") or "")
    plain = record.get("plainLyrics")
    if record.get("instrumental"):
        return -100
    if not plain or not str(plain).strip():
        return -100
    if "yeat" not in artist.casefold():
        return -100
    # Primary artist only — reject "Artist feat. Yeat" style rows.
    primary = artist.split(",")[0].split(" feat")[0].split(" ft")[0].strip()
    if fold_text(primary) != "yeat":
        return -80
    if is_dropped_title(title) or is_newer_project(album, title):
        return -50
    if not track_matches(job["title"], title):
        return -40

    score = 10
    if job["kind"] == "official":
        matched = match_official_album(album)
        if matched == job["album_key"]:
            score += 50
        elif matched:
            score += 5
        elif fold_text(album) in {"yeat", "yeat songs", "yeat videos", "yeat music", "null", ""}:
            score += 8
        else:
            score -= 5
    else:
        hints = [fold_text(h) for h in job.get("album_hints", ())]
        album_f = fold_text(album)
        if any(h and h in album_f for h in hints):
            score += 30
        elif album_f in {"yeat", "yeat songs", "yeat videos", "null", ""}:
            score += 15
        elif match_official_album(album):
            # Prefer the official copy if a "leak" title later landed on an album.
            score += 40
        else:
            score += 5

    # Prefer longer, non-truncated lyric bodies.
    chars = len(str(plain))
    if chars >= 400:
        score += 10
    elif chars >= 120:
        score += 5
    else:
        score -= 10
    return score
