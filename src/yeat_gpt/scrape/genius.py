"""Incremental Genius scrape. Existing HTML is never deleted."""

from __future__ import annotations

import asyncio
import json
import os
import random
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv
from tqdm import tqdm

from yeat_gpt.config import GENIUS_ARTIST, RAW_HTML_DIR, SCRAPE_STATUS_PATH

API_BASE_URL = "https://api.genius.com"
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


@dataclass
class GeniusSong:
    title: str
    url: str
    id: int


def existing_song_ids(html_dir: Path | None = None) -> set[int]:
    directory = html_dir or RAW_HTML_DIR
    found: set[int] = set()
    if not directory.exists():
        return found
    for path in directory.glob("*.html"):
        if path.stem.isdigit():
            found.add(int(path.stem))
    return found


def _html_path(song_id: int, html_dir: Path | None = None) -> Path:
    return (html_dir or RAW_HTML_DIR) / f"{song_id}.html"


def _write_status(payload: dict) -> None:
    SCRAPE_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCRAPE_STATUS_PATH.write_text(json.dumps(payload), encoding="utf-8")


def _atomic_html(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".html.tmp")
    tmp.write_text(text, encoding="utf-8", errors="replace")
    tmp.replace(path)


async def fetch_song_list(client: httpx.AsyncClient, artist_name: str) -> list[GeniusSong]:
    search = await client.get(f"{API_BASE_URL}/search", params={"q": artist_name})
    if search.status_code != 200:
        raise RuntimeError(f"Genius search failed with status {search.status_code}")
    hits = search.json()["response"]["hits"]
    artist_id = next(
        (
            hit["result"]["primary_artist"]["id"]
            for hit in hits
            if hit["result"]["primary_artist"]["name"].lower() == artist_name.lower()
        ),
        None,
    )
    if not artist_id:
        raise RuntimeError(f"Genius search did not find artist {artist_name}")
    songs: list[GeniusSong] = []
    page = 1
    with tqdm(desc="Fetching metadata", unit="page") as progress:
        while page:
            await asyncio.sleep(0.5)
            response = await client.get(
                f"{API_BASE_URL}/artists/{artist_id}/songs",
                params={"per_page": 50, "page": page, "sort": "popularity"},
            )
            if response.status_code != 200:
                raise RuntimeError(f"Genius song list failed with status {response.status_code}")
            data = response.json()["response"]
            for song in data["songs"]:
                if song["primary_artist"]["id"] == artist_id:
                    songs.append(GeniusSong(song["title"], song["url"], song["id"]))
            progress.update(1)
            page = data["next_page"]
    return songs


async def download_missing(
    client: httpx.AsyncClient,
    songs: list[GeniusSong],
    have_ids: set[int],
    album_filter: str | None = None,
) -> int:
    pending: list[GeniusSong] = []
    seen: set[int] = set()
    for song in songs:
        if song.id in have_ids or song.id in seen or _html_path(song.id).exists():
            continue
        seen.add(song.id)
        pending.append(song)
    if album_filter:
        needle = album_filter.lower()
        pending = [song for song in pending if needle in song.title.lower()]
    if not pending:
        return 0
    RAW_HTML_DIR.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for song in tqdm(pending, desc="Downloading lyrics", unit="song"):
        if _html_path(song.id).exists():
            continue
        retries = 3
        while retries > 0:
            try:
                await asyncio.sleep(random.uniform(5.0, 10.0))
                headers = {"User-Agent": random.choice(USER_AGENTS)}
                response = await client.get(song.url, headers=headers)
                if response.status_code in (403, 429, 1015):
                    tqdm.write(f"Rate limit — pausing 2 min (id {song.id})")
                    await asyncio.sleep(120)
                    retries -= 1
                    continue
                if response.status_code == 404:
                    break
                if response.status_code == 200:
                    _atomic_html(_html_path(song.id), response.text)
                    downloaded += 1
                    _write_status(
                        {
                            "phase": "downloading",
                            "listed": len(songs),
                            "already_present": len(have_ids),
                            "newly_downloaded": downloaded,
                            "pending": len(pending),
                        }
                    )
                    break
                tqdm.write(f"status {response.status_code} for id {song.id}")
            except httpx.HTTPError as exc:
                tqdm.write(f"Error: {type(exc).__name__}")
                await asyncio.sleep(5)
            retries -= 1
    return downloaded


async def _run_async(album_filter: str | None = None) -> dict[str, int]:
    load_dotenv()
    token = os.getenv("GENIUS_CLIENT_ACCESS_TOKEN", "").strip()
    if not token or token == "your_genius_token_here":
        raise RuntimeError("Set GENIUS_CLIENT_ACCESS_TOKEN in .env")
    have_ids = existing_song_ids()
    _write_status({"phase": "listing", "already_present": len(have_ids), "newly_downloaded": 0})
    headers = {"Authorization": f"Bearer {token}", "User-Agent": random.choice(USER_AGENTS)}
    async with httpx.AsyncClient(headers=headers, timeout=30) as api_client:
        songs = await fetch_song_list(api_client, GENIUS_ARTIST)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as web_client:
        new_count = await download_missing(web_client, songs, have_ids, album_filter)
    stats = {
        "listed": len(songs),
        "already_present": len(have_ids),
        "newly_downloaded": new_count,
    }
    _write_status({"phase": "done", **stats})
    return stats


def run_scrape(album_filter: str | None = None) -> dict[str, int]:
    return asyncio.run(_run_async(album_filter))
