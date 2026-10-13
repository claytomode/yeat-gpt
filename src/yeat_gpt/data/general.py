"""Stream a modest slice of UltraChat for the non-Yeat half of SFT."""

from __future__ import annotations

from pathlib import Path

from yeat_gpt.config import GENERAL_PATH
from yeat_gpt.jsonl import write_jsonl


def _mostly_english(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    if len(letters) < 8:
        return False
    ascii_letters = sum(1 for char in letters if char.isascii())
    if ascii_letters / len(letters) < 0.97:
        return False
    lowered = text.casefold()
    return any(word in lowered.split() for word in ("the", "a", "to", "you", "i", "is", "and"))


def _short_pair(user: str, assistant: str) -> bool:
    if "```" in user or "```" in assistant:
        return False
    if not (12 <= len(user) <= 400 and 40 <= len(assistant) <= 700):
        return False
    user_words = user.split()
    assistant_words = assistant.split()
    if not (3 <= len(user_words) <= 80 and 8 <= len(assistant_words) <= 130):
        return False
    return _mostly_english(user) and _mostly_english(assistant)


def _first_exchange(row: dict) -> tuple[str, str] | None:
    messages = row.get("messages")
    if isinstance(messages, list):
        user = None
        for message in messages:
            if not isinstance(message, dict):
                continue
            content = str(message.get("content") or "").strip()
            role = message.get("role")
            if role == "user" and user is None and content:
                user = content
            elif role == "assistant" and user and content:
                return user, content
        return None
    user = str(row.get("prompt") or row.get("user") or "").strip()
    assistant = str(row.get("response") or row.get("assistant") or "").strip()
    if user and assistant:
        return user, assistant
    return None


def fetch_general(count: int = 2500, dest: Path | None = None) -> int:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise ModuleNotFoundError(
            "datasets is not installed. Run: uv sync --extra general"
        ) from exc
    dataset = load_dataset("HuggingFaceH4/ultrachat_200k", split="train_sft", streaming=True)
    kept: list[dict] = []
    scanned = 0
    for row in dataset:
        scanned += 1
        if not isinstance(row, dict):
            continue
        pair = _first_exchange(row)
        if pair and _short_pair(pair[0], pair[1]):
            kept.append({"user": pair[0], "assistant": pair[1]})
        if len(kept) >= count:
            break
        if scanned >= 250_000:
            break
        if scanned % 5000 == 0:
            print(f"scanned={scanned} kept={len(kept)}")
    if len(kept) < 500:
        raise RuntimeError(
            f"Only kept {len(kept)} short English pairs after scanning {scanned} rows. "
            "Not writing a general file."
        )
    path = dest or GENERAL_PATH
    write_jsonl(path, kept)
    print(f"Wrote {len(kept)} pairs to {path} after scanning {scanned}")
    return len(kept)
