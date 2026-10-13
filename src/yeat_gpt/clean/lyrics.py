"""Parse Genius HTML and keep Yeat's sections as text."""

from __future__ import annotations

import json
import re
from pathlib import Path

from lxml import html as lxml_html

from yeat_gpt.clean.adlibs import filter_lines
from yeat_gpt.clean.style import save_lexicons
from yeat_gpt.config import (
    CATALOG_PATH,
    MANIFEST_PATH,
    PHRASE_BANK_PATH,
    PROCESSED_DIR,
    RAW_HTML_DIR,
    RAW_TEXT_DIR,
    STYLE_LEXICON_PATH,
)
from yeat_gpt.data.schema import CatalogEntry
from yeat_gpt.jsonl import read_jsonl

_HEADER_RE = re.compile(r"\[([^\[\]]+:[^\[\]]*)\]")
_NOISE_PHRASES = (
    "You might also like",
    "Contributors",
    "Songs Like",
    "Translations",
)


def _style_for_header(inner: str) -> str | None:
    low = inner.lower()
    if "yeat" not in low:
        return "SKIP"
    if "italic" in low:
        return "i"
    if "bold" in low:
        return "b"
    return None


def _take_text(
    final: list[str],
    text: str,
    style: str | None,
    *,
    text_node: bool,
    tag: str | None,
) -> None:
    if not text or style == "SKIP":
        return
    if text_node:
        if style is None:
            final.append(text)
        return
    if tag is not None and (style is None or tag == style):
        final.append(text)


def _consume_headers(
    text: str,
    style: str | None,
    final: list[str],
    *,
    text_node: bool,
    tag: str | None,
) -> str | None:
    """Split one node that may contain several [Verse: ...] headers."""
    parts = _HEADER_RE.split(text)
    if parts[0]:
        _take_text(final, parts[0], style, text_node=text_node, tag=tag)
    index = 1
    while index < len(parts):
        style = _style_for_header(parts[index])
        following = parts[index + 1] if index + 1 < len(parts) else ""
        if following:
            _take_text(final, following, style, text_node=text_node, tag=tag)
        index += 2
    return style


def process_lyrics_with_styles(lyric_containers) -> str:
    final_lyrics: list[str] = []
    for container in lyric_containers:
        style: str | None = None
        for element in container.xpath("./* | ./text()"):
            is_text = isinstance(element, str)
            text_val = element if is_text else element.text_content()
            tag = None if is_text else element.tag
            if _HEADER_RE.search(text_val or ""):
                style = _consume_headers(
                    text_val,
                    style,
                    final_lyrics,
                    text_node=is_text,
                    tag=tag,
                )
                if not is_text and tag == "br" and style != "SKIP":
                    final_lyrics.append("\n")
                continue
            if style == "SKIP":
                continue
            if is_text:
                if style is None and text_val:
                    final_lyrics.append(text_val)
            else:
                if style is None or tag == style:
                    content = element.text_content()
                    if content:
                        final_lyrics.append(content)
                if tag == "br":
                    final_lyrics.append("\n")
    return "".join(final_lyrics)


def clean_raw_text(raw_text: str) -> list[str]:
    """Strip Genius chrome and bracket headers. Keep parenthetical ad-libs."""
    text = re.sub(r"Read More[\s\S]*", "", raw_text)
    text = re.sub(r"\d*Embed$", "", text.strip())
    text = re.sub(r"\d+Embed", "", text)
    text = re.sub(r"\[[^\[\]]*\]", "", text)
    lines: list[str] = []
    for line in text.splitlines():
        for phrase in _NOISE_PHRASES:
            line = line.replace(phrase, "")
        clean_line = line.strip()
        if clean_line:
            lines.append(clean_line)
    return lines


def _title_from_html(path: Path) -> str:
    raw = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"<title>([^<]+)</title>", raw, re.IGNORECASE)
    if not match:
        return path.stem
    title = match.group(1)
    title = re.sub(r"\s*Lyrics\s*\|\s*Genius.*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*\|\s*Genius.*", "", title, flags=re.IGNORECASE)
    return title.strip() or path.stem


def _lyric_containers(tree):
    containers = tree.xpath('//div[@data-lyrics-container="true"]')
    if containers:
        return containers
    containers = tree.xpath('//*[contains(@class, "Lyrics__Container")]')
    if containers:
        return containers
    return tree.xpath('//*[@data-lyrics-container="true"]')


def parse_html_file(path: Path, title: str, genius_id: int, url: str) -> CatalogEntry | None:
    raw = path.read_text(encoding="utf-8", errors="replace")
    tree = lxml_html.fromstring(raw)
    containers = _lyric_containers(tree)
    if not containers:
        return None
    raw_text = process_lyrics_with_styles(containers)
    lines = clean_raw_text(raw_text)
    verse_lines, _stats = filter_lines(lines, for_verse=False)
    if not verse_lines:
        return None
    return CatalogEntry(
        genius_id=genius_id,
        title=title,
        url=url,
        text="\n".join(verse_lines),
        line_count=len(verse_lines),
    )


def _manifest_by_id() -> dict[int, dict]:
    found: dict[int, dict] = {}
    for row in read_jsonl(MANIFEST_PATH):
        genius_id = row.get("genius_id")
        if isinstance(genius_id, int):
            found[genius_id] = row
    return found


def _entry_from_text(path: Path, title: str, genius_id: int, url: str) -> CatalogEntry | None:
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = clean_raw_text(raw)
    verse_lines, _stats = filter_lines(lines, for_verse=False)
    if not verse_lines:
        return None
    return CatalogEntry(
        genius_id=genius_id,
        title=title,
        url=url,
        text="\n".join(verse_lines),
        line_count=len(verse_lines),
    )


def run_clean() -> dict[str, int]:
    """Parse imported HTML and any text imports into one catalog."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    manifest = _manifest_by_id()
    entries: list[CatalogEntry] = []
    html_used = 0
    text_used = 0
    skipped = 0

    if RAW_HTML_DIR.exists():
        for path in sorted(RAW_HTML_DIR.glob("*.html")):
            stem = path.stem
            genius_id = int(stem) if stem.isdigit() else 0
            meta = manifest.get(genius_id, {})
            title = str(meta.get("title") or _title_from_html(path))
            url = str(meta.get("url") or "")
            if genius_id and not url:
                url = f"https://genius.com/songs/{genius_id}"
            try:
                entry = parse_html_file(path, title, genius_id, url)
            except Exception:
                skipped += 1
                continue
            if entry is None:
                skipped += 1
                continue
            entries.append(entry)
            html_used += 1

    text_manifest = {
        str(row.get("path")): row
        for row in read_jsonl(MANIFEST_PATH)
        if row.get("path") and not isinstance(row.get("genius_id"), int)
    }
    if RAW_TEXT_DIR.exists():
        for path in sorted(RAW_TEXT_DIR.glob("*.txt")):
            meta = text_manifest.get(path.name, {})
            title = str(meta.get("title") or path.stem)
            url = str(meta.get("url") or "")
            try:
                entry = _entry_from_text(path, title, 0, url)
            except Exception:
                skipped += 1
                continue
            if entry is None:
                skipped += 1
                continue
            entries.append(entry)
            text_used += 1

    songs = [entry.to_dict() for entry in entries]
    CATALOG_PATH.write_text(json.dumps(songs, indent=2, ensure_ascii=False), encoding="utf-8")
    save_lexicons(songs, STYLE_LEXICON_PATH, PHRASE_BANK_PATH)
    return {
        "songs_cleaned": len(entries),
        "from_html": html_used,
        "from_text": text_used,
        "skipped": skipped,
    }
