"""Load the persona and rewrite instructions."""

from __future__ import annotations

from yeat_gpt.config import REWRITE_PROMPT_PATH, SYSTEM_PROMPT_PATH


def load_system_prompt() -> str:
    if not SYSTEM_PROMPT_PATH.is_file():
        raise FileNotFoundError(f"Missing persona prompt: {SYSTEM_PROMPT_PATH}")
    text = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"Persona prompt is empty: {SYSTEM_PROMPT_PATH}")
    return text


def load_rewrite_prompt() -> str:
    if not REWRITE_PROMPT_PATH.is_file():
        raise FileNotFoundError(f"Missing rewrite prompt: {REWRITE_PROMPT_PATH}")
    text = REWRITE_PROMPT_PATH.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"Rewrite prompt is empty: {REWRITE_PROMPT_PATH}")
    return text
