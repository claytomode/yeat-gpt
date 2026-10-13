"""Conversational SFT rows. Assistant turns are English in voice, not raw bars."""

from __future__ import annotations

import json
import random
from pathlib import Path

from yeat_gpt.config import (
    BREAK_PREFIX,
    CATALOG_PATH,
    GENERAL_PATH,
    GENERAL_SYSTEM,
    REWRITE_BATCH_PATH,
    REWRITES_PATH,
    SFT_PATH,
    YEAT_SOURCES,
)
from yeat_gpt.data.rewrite import CONTINUATION_USERS, accept_rewrite, update_rewrite_batch
from yeat_gpt.jsonl import read_jsonl, write_jsonl
from yeat_gpt.prompts import load_system_prompt

GREETING_USERS = (
    "hey what's good",
    "how are you doing",
    "you up right now",
)
GREETING_LEADS = (
    "I am good. Just been moving through the day.",
    "Yeah I am here. Tell me what you need.",
    "I am straight. Been quiet and locked in.",
)
OPINION_USERS = (
    "what do you think about {topic}",
    "how do you feel about {topic}",
    "you into {topic} or what",
)
OPINION_LEADS = (
    "I like {topic}. It sits right with me.",
    "Yeah I mess with {topic} when it feels honest.",
    "I keep {topic} simple and I mean that.",
)
EXPLAIN_USERS = (
    "what did you mean by that",
    "explain that in normal words",
    "say it so I can follow",
)
EXPLAIN_LEADS = (
    "I meant that I stay on my own path and I do not chase the noise.",
    "Yeah I was saying the night moves fast and I move with it.",
    "I was talking about finishing what I started.",
)
TOPICS = ("night drives", "the city", "working late", "new music", "quiet rooms")
MISSING_GENERAL = """Not writing data/processed/sft.jsonl because general instruct data is missing.
Next: uv sync --extra general
Then: uv run yeat-gpt fetch-general
Then: uv run yeat-gpt build"""


def song_lines(song: dict) -> list[str]:
    return [line.strip() for line in str(song.get("text") or "").splitlines() if line.strip()]


def _message(system: str, user: str, assistant: str, source: str, **extra) -> dict:
    row = {
        "source": source,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ],
    }
    row.update(extra)
    return row


def _one_template(song: dict, rng: random.Random, system: str) -> dict | None:
    lines = song_lines(song)
    if not lines:
        return None
    variant = rng.choice(("greeting", "opinion", "explain"))
    topic = rng.choice(TOPICS)
    if variant == "greeting":
        user = rng.choice(GREETING_USERS)
        lead = rng.choice(GREETING_LEADS)
        include_bar = rng.random() < 0.55
    elif variant == "opinion":
        user = rng.choice(OPINION_USERS).format(topic=topic)
        lead = rng.choice(OPINION_LEADS).format(topic=topic)
        include_bar = rng.random() < 0.55
    else:
        user = rng.choice(EXPLAIN_USERS)
        lead = rng.choice(EXPLAIN_LEADS)
        include_bar = rng.random() < 0.15
    assistant = lead
    if include_bar:
        assistant = f"{lead}\n{rng.choice(lines)}"
    if assistant.strip() in set(lines):
        return None
    return _message(system, user, assistant, "template", variant=variant)


def build_template_rows(
    songs: list[dict],
    *,
    limit: int,
    rng: random.Random,
    system: str,
) -> list[dict]:
    if limit <= 0 or not songs:
        return []
    rows: list[dict] = []
    attempts = 0
    while len(rows) < limit and attempts < limit * 30:
        attempts += 1
        row = _one_template(rng.choice(songs), rng, system)
        if row:
            rows.append(row)
    return rows


def _consecutive(lines: list[str], rng: random.Random) -> list[str] | None:
    if len(lines) < 2:
        return None
    count = rng.randint(2, min(4, len(lines)))
    start = rng.randint(0, len(lines) - count)
    return lines[start : start + count]


def build_continuation_rows(
    songs: list[dict],
    *,
    limit: int,
    rng: random.Random,
    system: str,
) -> list[dict]:
    if limit <= 0 or not songs:
        return []
    rows: list[dict] = []
    attempts = 0
    while len(rows) < limit and attempts < limit * 40:
        attempts += 1
        song = rng.choice(songs)
        chunk = _consecutive(song_lines(song), rng)
        if not chunk:
            continue
        rows.append(
            _message(system, rng.choice(CONTINUATION_USERS), "\n".join(chunk), "continuation")
        )
    return rows


def rows_from_rewrites(rewrites: list[dict], batch_rows: list[dict], system: str) -> list[dict]:
    by_id = {row.get("id"): row for row in batch_rows}
    out: list[dict] = []
    for item in rewrites:
        source = by_id.get(item.get("id"))
        assistant = str(item.get("assistant") or "").strip()
        if not source or not assistant:
            continue
        bars = [str(bar) for bar in source.get("bars") or []]
        ok, _reason = accept_rewrite(assistant, bars)
        if not ok:
            continue
        out.append(_message(system, str(source.get("user") or ""), assistant, "rewrite"))
    return out


def mix_rows(
    yeat_rows: list[dict],
    general_pairs: list[dict],
    *,
    rng: random.Random,
    persona: str,
) -> list[dict]:
    """About 60% yeat rows and 40% general, with 10% of that side as a persona escape hatch."""
    yeat = [row for row in yeat_rows if row.get("source") in YEAT_SOURCES]
    general = [
        pair
        for pair in general_pairs
        if str(pair.get("user") or "").strip() and str(pair.get("assistant") or "").strip()
    ]
    if not yeat or not general:
        return []
    rng.shuffle(yeat)
    rng.shuffle(general)
    n_other = round(len(yeat) * 40 / 60)
    if len(general) < max(n_other, 1):
        n_other = len(general)
        n_yeat = min(len(yeat), round(n_other * 60 / 40))
        yeat = yeat[:n_yeat]
    else:
        n_other = max(n_other, 1)
        general = general[:n_other]
    n_break = round(0.10 * n_other)
    if n_break >= n_other:
        n_break = n_other - 1
    if n_other >= 10 and n_break < 1:
        n_break = 1
    mixed: list[dict] = list(yeat)
    for index, pair in enumerate(general):
        user = str(pair["user"]).strip()
        assistant = str(pair["assistant"]).strip()
        if index < n_break:
            mixed.append(
                _message(persona, BREAK_PREFIX + user, assistant, "break")
            )
        else:
            mixed.append(_message(GENERAL_SYSTEM, user, assistant, "general"))
    rng.shuffle(mixed)
    return mixed


def assistant_text(row: dict) -> str:
    for message in row.get("messages") or []:
        if message.get("role") == "assistant":
            return str(message.get("content") or "").strip()
    return ""


def assess_rows(rows: list[dict], corpus_lines: list[str] | None = None) -> list[str]:
    """Return human-readable failures. An empty list means the mix is trainable."""
    problems: list[str] = []
    if not rows:
        return ["sft.jsonl has no rows"]
    yeat = [row for row in rows if row.get("source") in YEAT_SOURCES]
    general = [row for row in rows if row.get("source") == "general"]
    if not general:
        problems.append("no general rows")
    ratio = len(yeat) / len(rows)
    if not (0.50 <= ratio <= 0.70):
        problems.append(f"yeat ratio {ratio:.3f} is outside 0.50-0.70")
    if yeat:
        continuations = sum(1 for row in yeat if row.get("source") == "continuation")
        share = continuations / len(yeat)
        if share > 0.35:
            problems.append(f"continuation share of yeat rows is {share:.3f}, above 0.35")
    if corpus_lines is not None:
        corpus = {line.strip() for line in corpus_lines if line.strip()}
        pool = [row for row in rows if row.get("source") in {"template", "rewrite"}]
        if pool and corpus:
            exact = sum(1 for row in pool if assistant_text(row) in corpus)
            share = exact / len(pool)
            if share > 0.15:
                problems.append(
                    f"template/rewrite assistants that exactly equal corpus lines are {share:.3f}"
                )
    return problems


def load_catalog(path: Path | None = None) -> list[dict]:
    catalog = path or CATALOG_PATH
    if not catalog.is_file():
        raise FileNotFoundError(f"Missing {catalog}. Run: uv run yeat-gpt clean")
    payload = json.loads(catalog.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"{catalog} has no songs. Run clean on imported lyrics first.")
    return payload


def corpus_lines_from_catalog(songs: list[dict]) -> list[str]:
    lines: list[str] = []
    for song in songs:
        lines.extend(song_lines(song))
    return lines


def run_check(
    sft_path: Path | None = None,
    catalog_path: Path | None = None,
) -> list[str]:
    path = sft_path or SFT_PATH
    if not path.is_file():
        return [f"sft.jsonl is missing: {path}"]
    rows = read_jsonl(path)
    catalog = catalog_path or CATALOG_PATH
    corpus: list[str] | None = None
    if catalog.is_file():
        try:
            songs = json.loads(catalog.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            songs = []
        if isinstance(songs, list) and songs:
            corpus = corpus_lines_from_catalog(songs)
    return assess_rows(rows, corpus)


def build_sft(
    *,
    max_templates: int = 2000,
    continuation_fraction: float = 0.15,
    rewrite_batch: int = 500,
    seed: int = 42,
    catalog_path: Path | None = None,
    general_path: Path | None = None,
    sft_path: Path | None = None,
    batch_path: Path | None = None,
    rewrites_path: Path | None = None,
) -> dict[str, int]:
    if not 0 < continuation_fraction < 0.35:
        raise ValueError("continuation fraction must stay under 0.35")
    songs = load_catalog(catalog_path)
    persona = load_system_prompt()
    rng = random.Random(seed)
    batch_file = batch_path or REWRITE_BATCH_PATH
    rewrite_file = rewrites_path or REWRITES_PATH
    out_path = sft_path or SFT_PATH
    general_file = general_path or GENERAL_PATH

    batch = update_rewrite_batch(songs, limit=rewrite_batch, rng=rng, path=batch_file)
    rewrites = read_jsonl(rewrite_file)
    rewrite_rows = rows_from_rewrites(rewrites, batch, persona)
    template_limit = max_templates
    if rewrite_rows:
        template_limit = min(template_limit, len(rewrite_rows))
    templates = build_template_rows(songs, limit=template_limit, rng=rng, system=persona)
    base = templates + rewrite_rows
    n_cont = 0
    if base:
        n_cont = round(len(base) * continuation_fraction / (1 - continuation_fraction))
    continuations = build_continuation_rows(songs, limit=n_cont, rng=rng, system=persona)
    yeat_rows = base + continuations
    stats = {
        "templates": len(templates),
        "rewrites": len(rewrite_rows),
        "continuations": len(continuations),
        "rewrite_batch": len(batch),
        "sft": 0,
    }
    if not general_file.is_file() or not read_jsonl(general_file):
        print(MISSING_GENERAL)
        return stats
    mixed = mix_rows(yeat_rows, read_jsonl(general_file), rng=rng, persona=persona)
    if not mixed:
        print(MISSING_GENERAL)
        return stats
    write_jsonl(out_path, mixed)
    stats["sft"] = len(mixed)
    return stats
