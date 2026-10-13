"""Fetch plain Yeat lyrics from LRCLIB. No Genius token required."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
from tqdm import tqdm

from yeat_gpt.config import RAW_DIR, SCRAPE_STATUS_PATH
from yeat_gpt.scrape.scope import score_candidate, wanted_track_queries

LRCLIB_BASE = "https://lrclib.net"
USER_AGENT = "YeatGPT/0.3.0 (research pipeline; contact: local)"
RAW_LRCLIB_DIR = RAW_DIR / "lrclib"
MANIFEST_PATH = RAW_DIR / "lrclib_manifest.jsonl"


def _write_status(payload: dict) -> None:
    SCRAPE_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCRAPE_STATUS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _append_manifest(row: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MANIFEST_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def existing_ids(directory: Path | None = None) -> set[int]:
    root = directory or RAW_LRCLIB_DIR
    found: set[int] = set()
    if not root.exists():
        return found
    for path in root.glob("*.json"):
        if path.stem.isdigit():
            found.add(int(path.stem))
    return found


def _get_json(client: httpx.Client, path: str, params: dict) -> list | dict | None:
    for attempt in range(8):
        try:
            response = client.get(path, params=params)
        except httpx.HTTPError:
            time.sleep(1.5 * (attempt + 1))
            continue
        if response.status_code == 429:
            retry = int(response.headers.get("Retry-After") or "2")
            time.sleep(max(retry, 1) + attempt)
            continue
        if response.status_code in {500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526}:
            time.sleep(2.0 * (attempt + 1))
            continue
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            # Soft-fail a single search rather than aborting the whole scrape.
            return [] if path.endswith("/search") else None
        return response.json()
    return [] if path.endswith("/search") else None


def _ascii_title(title: str) -> str:
    from yeat_gpt.scrape.scope import fold_text

    return fold_text(title)


def search_track(client: httpx.Client, title: str) -> list[dict]:
    queries = [title]
    ascii_name = _ascii_title(title)
    if ascii_name and ascii_name.casefold() != title.casefold():
        queries.append(ascii_name)

    found: list[dict] = []
    seen: set[int] = set()
    for query in queries:
        data = _get_json(
            client,
            "/api/search",
            {"track_name": query, "artist_name": "Yeat"},
        )
        rows = data if isinstance(data, list) else []
        if not rows:
            data = _get_json(client, "/api/search", {"q": f"Yeat {query}"})
            rows = data if isinstance(data, list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                row_id = int(row["id"])
            except (KeyError, TypeError, ValueError):
                continue
            if row_id in seen:
                continue
            seen.add(row_id)
            found.append(row)
        if found:
            break
        time.sleep(0.2)
    return found


def pick_best(job: dict, records: list[dict]) -> dict | None:
    best: dict | None = None
    best_score = 0
    for record in records:
        score = score_candidate(job, record)
        if score > best_score:
            best = record
            best_score = score
    return best


def run_scrape(*, sleep_s: float = 0.35) -> dict[str, int]:
    """Download in-scope Yeat plain lyrics into data/raw/lrclib/{id}.json."""
    RAW_LRCLIB_DIR.mkdir(parents=True, exist_ok=True)
    jobs = wanted_track_queries()
    have = existing_ids()
    listed = len(jobs)
    newly = 0
    skipped_existing = 0
    missed = 0
    seen_ids: set[int] = set(have)

    _write_status(
        {
            "phase": "lrclib",
            "listed": listed,
            "already_present": len(have),
            "newly_downloaded": 0,
        }
    )

    headers = {"User-Agent": USER_AGENT, "Lrclib-Client": USER_AGENT}
    with httpx.Client(base_url=LRCLIB_BASE, headers=headers, timeout=30.0) as client:
        for job in tqdm(jobs, desc="LRCLIB tracks", unit="track"):
            records = search_track(client, job["title"])
            time.sleep(sleep_s)
            best = pick_best(job, records)
            if best is None:
                missed += 1
                continue
            track_id = int(best["id"])
            path = RAW_LRCLIB_DIR / f"{track_id}.json"
            if track_id in seen_ids or path.exists():
                skipped_existing += 1
                continue
            payload = {
                "id": track_id,
                "title": best.get("trackName") or best.get("name") or job["title"],
                "artist": best.get("artistName") or "Yeat",
                "album": best.get("albumName") or job["album_label"],
                "duration": best.get("duration"),
                "plainLyrics": best.get("plainLyrics"),
                "source": "lrclib",
                "scope_kind": job["kind"],
                "scope_album_key": job["album_key"],
                "scope_album_label": job["album_label"],
                "query_title": job["title"],
            }
            _atomic_json(path, payload)
            _append_manifest(
                {
                    "id": track_id,
                    "title": payload["title"],
                    "album": payload["album"],
                    "scope_kind": job["kind"],
                    "scope_album_key": job["album_key"],
                    "path": path.name,
                }
            )
            seen_ids.add(track_id)
            newly += 1
            _write_status(
                {
                    "phase": "lrclib",
                    "listed": listed,
                    "already_present": len(have),
                    "newly_downloaded": newly,
                    "missed": missed,
                    "skipped_existing": skipped_existing,
                }
            )

    stats = {
        "listed": listed,
        "already_present": len(have),
        "newly_downloaded": newly,
        "missed": missed,
        "skipped_existing": skipped_existing,
    }
    _write_status({"phase": "done", **stats})
    return stats
