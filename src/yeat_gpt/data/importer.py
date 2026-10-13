"""Import lyric snapshots without deleting songs already on disk."""

from __future__ import annotations

import json
import pickle
import re
import zipfile
from pathlib import Path

from yeat_gpt.config import MANIFEST_PATH, RAW_HTML_DIR, RAW_TEXT_DIR

_EOT = "<|endoftext|>"
_RECOGNIZED = {".pkl", ".pickle", ".html", ".htm", ".txt", ".json", ".jsonl", ".zip"}


class ForeignSong:
    """Stand-in for a Song class pickled from another module, including __main__."""

    def __init__(self, title=None, url=None, id=None, **kwargs):
        self.title = title
        self.url = url
        self.id = id
        self.__dict__.update(kwargs)

    def __setstate__(self, state) -> None:
        if isinstance(state, dict):
            self.__dict__.update(state)
            return
        if isinstance(state, tuple):
            for part in state:
                if isinstance(part, dict):
                    self.__dict__.update(part)
            return
        raise TypeError(f"Unexpected Song pickle state: {type(state).__name__}")


class _SafeUnpickler(pickle.Unpickler):
    _SAFE_MODULES = {"builtins", "__builtin__", "collections", "copyreg", "copy_reg"}

    def find_class(self, module: str, name: str):
        if name == "Song":
            return ForeignSong
        if module in self._SAFE_MODULES:
            return super().find_class(module, name)
        raise pickle.UnpicklingError(f"Refusing to unpickle {module}.{name}")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(text.encode("utf-8", errors="replace"))
    tmp.replace(path)


def _append_manifest(record: dict, manifest_path: Path | None) -> None:
    path = manifest_path or MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _song_fields(song) -> tuple[str, str, int]:
    if isinstance(song, dict):
        title = str(song.get("title") or "")
        url = str(song.get("url") or "")
        raw_id = song.get("id", song.get("genius_id"))
    else:
        title = str(getattr(song, "title", "") or "")
        url = str(getattr(song, "url", "") or "")
        raw_id = getattr(song, "id", None)
    if raw_id is None:
        raise ValueError("Song record has no id")
    return title, url, int(raw_id)


def _html_from_entry(entry: dict) -> str:
    html = entry.get("html")
    if html is None:
        html = entry.get("HTML")
    if not isinstance(html, str) or not html.strip():
        raise ValueError("Pickle entry is missing html")
    return html


def import_pickle(
    path: Path,
    *,
    html_dir: Path | None = None,
    text_dir: Path | None = None,
    manifest_path: Path | None = None,
) -> dict[str, int]:
    html_dir = html_dir or RAW_HTML_DIR
    html_dir.mkdir(parents=True, exist_ok=True)
    print(f"Loading {path.name}")
    with path.open("rb") as handle:
        payload = _SafeUnpickler(handle).load()
    print(f"Loaded {len(payload) if isinstance(payload, list) else 0} records")
    if not isinstance(payload, list):
        raise ValueError(f"{path} is not a list of song records")
    written = 0
    skipped = 0
    failed = 0
    for entry in payload:
        if not isinstance(entry, dict) or "song" not in entry:
            failed += 1
            continue
        try:
            title, url, song_id = _song_fields(entry["song"])
            html = _html_from_entry(entry)
        except (TypeError, ValueError):
            failed += 1
            continue
        dest = html_dir / f"{song_id}.html"
        if dest.exists():
            skipped += 1
            continue
        _atomic_write(dest, html)
        _append_manifest(
            {
                "genius_id": song_id,
                "title": title,
                "url": url,
                "source": "pickle",
            },
            manifest_path,
        )
        written += 1
    return {"html_written": written, "skipped": skipped, "failed": failed, "text_written": 0}


def _write_text_song(
    text_dir: Path,
    *,
    index: int,
    title: str,
    body: str,
    url: str,
    source: str,
    manifest_path: Path | None,
) -> bool:
    text_dir.mkdir(parents=True, exist_ok=True)
    name = f"{index:04d}.txt"
    dest = text_dir / name
    if dest.exists():
        return False
    _atomic_write(dest, body.strip() + "\n")
    _append_manifest(
        {
            "genius_id": None,
            "title": title or name,
            "url": url,
            "source": source,
            "path": name,
        },
        manifest_path,
    )
    return True


def import_text(
    path: Path,
    *,
    html_dir: Path | None = None,
    text_dir: Path | None = None,
    manifest_path: Path | None = None,
) -> dict[str, int]:
    text_dir = text_dir or RAW_TEXT_DIR
    raw = path.read_text(encoding="utf-8", errors="replace")
    parts = [part.strip() for part in raw.split(_EOT)]
    parts = [part for part in parts if part]
    written = 0
    skipped = 0
    for index, part in enumerate(parts, start=1):
        title = part.splitlines()[0][:80] if part.splitlines() else f"song-{index}"
        if _write_text_song(
            text_dir,
            index=index,
            title=title,
            body=part,
            url="",
            source="txt",
            manifest_path=manifest_path,
        ):
            written += 1
        else:
            skipped += 1
    return {"html_written": 0, "text_written": written, "skipped": skipped, "failed": 0}


def _records_from_json(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        return []
    if path.suffix == ".jsonl":
        rows = []
        for line in raw.splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    payload = json.loads(raw)
    if isinstance(payload, dict):
        return [payload]
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    raise ValueError(f"{path} must be an object, a list, or JSONL")


def import_json(
    path: Path,
    *,
    html_dir: Path | None = None,
    text_dir: Path | None = None,
    manifest_path: Path | None = None,
) -> dict[str, int]:
    text_dir = text_dir or RAW_TEXT_DIR
    written = 0
    skipped = 0
    failed = 0
    for index, row in enumerate(_records_from_json(path), start=1):
        body = row.get("text")
        if body is None:
            body = row.get("lyrics")
        if not isinstance(body, str) or not body.strip():
            failed += 1
            continue
        title = str(row.get("title") or f"song-{index}")
        url = str(row.get("url") or "")
        if _write_text_song(
            text_dir,
            index=index,
            title=title,
            body=body,
            url=url,
            source=path.suffix.lstrip("."),
            manifest_path=manifest_path,
        ):
            written += 1
        else:
            skipped += 1
    return {"html_written": 0, "text_written": written, "skipped": skipped, "failed": failed}


def import_html_file(
    path: Path,
    *,
    html_dir: Path | None = None,
    text_dir: Path | None = None,
    manifest_path: Path | None = None,
) -> dict[str, int]:
    html_dir = html_dir or RAW_HTML_DIR
    html_dir.mkdir(parents=True, exist_ok=True)
    stem = path.stem if path.stem.isdigit() else re.sub(r"[^\w.-]+", "_", path.stem)[:80]
    dest = html_dir / f"{stem}{path.suffix.lower() if path.suffix.lower() == '.html' else '.html'}"
    if dest.exists():
        return {"html_written": 0, "text_written": 0, "skipped": 1, "failed": 0}
    _atomic_write(dest, path.read_text(encoding="utf-8", errors="replace"))
    if stem.isdigit():
        _append_manifest(
            {
                "genius_id": int(stem),
                "title": path.stem,
                "url": "",
                "source": "html",
            },
            manifest_path,
        )
    return {"html_written": 1, "text_written": 0, "skipped": 0, "failed": 0}


def _merge(total: dict[str, int], part: dict[str, int]) -> None:
    for key, value in part.items():
        total[key] = total.get(key, 0) + int(value)


def import_zip(path: Path, **kwargs) -> dict[str, int]:
    dest = path.parent / f".import-{path.stem}"
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        root = dest.resolve()
        for info in archive.infolist():
            target = (dest / info.filename).resolve()
            if not str(target).startswith(str(root)):
                raise ValueError(f"Unsafe path in zip: {info.filename}")
        archive.extractall(dest)
    return import_path(dest, **kwargs)


def import_file(path: Path, **kwargs) -> dict[str, int]:
    suffix = path.suffix.lower()
    if suffix in {".pkl", ".pickle"}:
        return import_pickle(path, **kwargs)
    if suffix == ".txt":
        return import_text(path, **kwargs)
    if suffix in {".json", ".jsonl"}:
        return import_json(path, **kwargs)
    if suffix in {".html", ".htm"}:
        return import_html_file(path, **kwargs)
    if suffix == ".zip":
        return import_zip(path, **kwargs)
    raise ValueError(
        f"Cannot import {path.name}. Use a pickle, HTML file or directory, "
        "text split on <|endoftext|>, JSON/JSONL, or a zip of those."
    )


def import_path(path: Path, **kwargs) -> dict[str, int]:
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Nothing to import at {path}")
    if path.is_file():
        return import_file(path, **kwargs)
    total = {"html_written": 0, "text_written": 0, "skipped": 0, "failed": 0}
    found = False
    for child in sorted(path.rglob("*")):
        if not child.is_file() or child.suffix.lower() not in _RECOGNIZED:
            continue
        if dest_name(child, path):
            continue
        found = True
        _merge(total, import_file(child, **kwargs))
    if not found:
        raise ValueError(f"No pickle, HTML, text, or JSON lyrics found in {path}")
    return total


def dest_name(child: Path, root: Path) -> bool:
    """Skip files written under a previous extract dir inside the source folder."""
    return ".import-" in str(child.relative_to(root))
