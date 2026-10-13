"""Rewrite-batch helpers and the optional OpenAI-compatible pass."""

from __future__ import annotations

import hashlib
import json
import os
import random
from pathlib import Path

import httpx
from dotenv import load_dotenv

from yeat_gpt.config import REWRITE_BATCH_PATH, REWRITES_PATH
from yeat_gpt.jsonl import read_jsonl, write_jsonl
from yeat_gpt.prompts import load_rewrite_prompt, load_system_prompt

CONTINUATION_USERS = (
    "give me a bar",
    "can you spit a few lines",
    "write me a verse",
    "drop some lines",
)
_BATCH_USERS = (
    "what you been on lately",
    "how was your night",
    "what is on your mind",
    "talk to me for a second",
)


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def accept_rewrite(assistant: str, bars: list[str]) -> tuple[bool, str]:
    """Reject empty, tiny, or verbatim-bar replies."""
    text = assistant.strip()
    if not text:
        return False, "empty"
    if len(text.split()) < 5 or len(text) < 24:
        return False, "too_short"
    banned = {_norm(bar) for bar in bars if str(bar).strip()}
    if bars:
        banned.add(_norm("\n".join(bars)))
        banned.add(_norm(" ".join(str(bar) for bar in bars)))
    if _norm(text) in banned:
        return False, "verbatim"
    return True, ""


def _rewrite_id(song: str, bars: list[str]) -> str:
    raw = song + "\n" + "\n".join(bars)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _one_batch_row(songs: list[dict], rng: random.Random, instruction: str) -> dict | None:
    from yeat_gpt.data.sft import _consecutive, song_lines

    song = rng.choice(songs)
    lines = song_lines(song)
    if len(lines) < 1:
        return None
    count = rng.randint(1, min(3, len(lines)))
    if count >= 2:
        chunk = _consecutive(lines, rng)
        if not chunk:
            return None
        bars = chunk[:count] if len(chunk) >= count else chunk
        if len(bars) < 1:
            return None
    else:
        bars = [rng.choice(lines)]
    title = str(song.get("title") or "song")
    return {
        "id": _rewrite_id(title, bars),
        "user": rng.choice(_BATCH_USERS),
        "bars": bars,
        "song": title,
        "instruction": instruction,
    }


def update_rewrite_batch(
    songs: list[dict],
    *,
    limit: int,
    rng: random.Random,
    path: Path | None = None,
) -> list[dict]:
    """Keep existing batch ids so an in-progress rewrite pass can resume."""
    batch_path = path or REWRITE_BATCH_PATH
    existing = read_jsonl(batch_path)
    rows: list[dict] = []
    seen: set[str] = set()
    for row in existing:
        row_id = str(row.get("id") or "")
        if row_id and row_id not in seen:
            rows.append(row)
            seen.add(row_id)
    instruction = load_rewrite_prompt()
    attempts = 0
    while len(rows) < limit and attempts < max(limit, 1) * 40:
        attempts += 1
        row = _one_batch_row(songs, rng, instruction)
        if not row or row["id"] in seen:
            continue
        rows.append(row)
        seen.add(row["id"])
    write_jsonl(batch_path, rows)
    return rows


def import_rewrite_file(
    path: Path,
    *,
    batch_path: Path | None = None,
    dest: Path | None = None,
) -> dict:
    batch_file = batch_path or REWRITE_BATCH_PATH
    if not batch_file.is_file():
        raise FileNotFoundError(f"Missing {batch_file}. Run: uv run yeat-gpt build")
    batch = {str(row.get("id")): row for row in read_jsonl(batch_file)}
    accepted: list[dict] = []
    rejected = 0
    for row in read_jsonl(path):
        row_id = str(row.get("id") or "")
        source = batch.get(row_id)
        assistant = str(row.get("assistant") or "")
        if source is None:
            rejected += 1
            continue
        bars = [str(bar) for bar in source.get("bars") or []]
        ok, _reason = accept_rewrite(assistant, bars)
        if not ok:
            rejected += 1
            continue
        accepted.append({"id": row_id, "assistant": assistant.strip()})
    out = dest or REWRITES_PATH
    merged = {str(row.get("id")): row for row in read_jsonl(out)}
    for row in accepted:
        merged[row["id"]] = row
    write_jsonl(out, list(merged.values()))
    return {"accepted": len(accepted), "rejected": rejected, "stored": len(merged)}


def _chat_url(base: str) -> str:
    cleaned = base.rstrip("/")
    if cleaned.endswith("/chat/completions"):
        return cleaned
    return cleaned + "/chat/completions"


def run_rewrite() -> int:
    load_dotenv()
    base = os.getenv("OPENAI_BASE_URL", "").strip()
    key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "").strip()
    if not base or not key or not model:
        print("Set OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL to run rewrites.")
        print(f"Batch file: {REWRITE_BATCH_PATH}")
        return 0
    if not REWRITE_BATCH_PATH.is_file():
        raise FileNotFoundError(f"Missing {REWRITE_BATCH_PATH}. Run: uv run yeat-gpt build")
    done = {str(row.get("id")) for row in read_jsonl(REWRITES_PATH)}
    system = load_system_prompt()
    written = 0
    REWRITES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with REWRITES_PATH.open("a", encoding="utf-8") as handle:
        for row in read_jsonl(REWRITE_BATCH_PATH):
            row_id = str(row.get("id") or "")
            if not row_id or row_id in done:
                continue
            bars = [str(bar) for bar in row.get("bars") or []]
            user = (
                f"{row.get('instruction') or load_rewrite_prompt()}\n\n"
                f"User said: {row.get('user')}\n"
                f"Bars:\n" + "\n".join(bars)
            )
            response = httpx.post(
                _chat_url(base),
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": model,
                    "temperature": 0.7,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                timeout=120,
            )
            response.raise_for_status()
            assistant = response.json()["choices"][0]["message"]["content"]
            ok, reason = accept_rewrite(str(assistant), bars)
            if not ok:
                print(f"skip {row_id}: {reason}")
                continue
            handle.write(
                json.dumps({"id": row_id, "assistant": str(assistant).strip()}, ensure_ascii=False)
                + "\n"
            )
            handle.flush()
            done.add(row_id)
            written += 1
    return written
