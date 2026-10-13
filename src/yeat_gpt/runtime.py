"""Ollama chat, Modelfile export, and the offline eval pack."""

from __future__ import annotations

from collections import Counter

import httpx

from yeat_gpt.config import EVAL_OUTPUTS_PATH, EVAL_PROMPTS_PATH, MODELFILE_PATH
from yeat_gpt.jsonl import read_jsonl, write_jsonl
from yeat_gpt.prompts import load_system_prompt

REQUIRED_CATEGORIES = (
    "english",
    "persona",
    "bars",
    "explain-without-bars",
    "multi-turn",
)
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"


def load_eval_prompts() -> list[dict]:
    if not EVAL_PROMPTS_PATH.is_file():
        raise FileNotFoundError(f"Missing eval pack: {EVAL_PROMPTS_PATH}")
    return read_jsonl(EVAL_PROMPTS_PATH)


def validate_eval_prompts(rows: list[dict]) -> list[str]:
    problems: list[str] = []
    if not 18 <= len(rows) <= 24:
        problems.append(f"expected about 20 prompts, found {len(rows)}")
    categories = {str(row.get("category") or "") for row in rows}
    for name in REQUIRED_CATEGORIES:
        if name not in categories:
            problems.append(f"missing category {name}")
    for row in rows:
        messages = row.get("messages")
        if not isinstance(messages, list) or not messages:
            problems.append(f"{row.get('id')} has no messages")
            continue
        if messages[-1].get("role") != "user":
            problems.append(f"{row.get('id')} must end on a user turn")
    return problems


def _with_persona(messages: list[dict], system: str) -> list[dict]:
    if messages and messages[0].get("role") == "system":
        return [{"role": "system", "content": system}, *messages[1:]]
    return [{"role": "system", "content": system}, *messages]


def ollama_chat(model: str, messages: list[dict]) -> str:
    try:
        response = httpx.post(
            OLLAMA_URL,
            json={"model": model, "messages": messages, "stream": False},
            timeout=180,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise RuntimeError(
            "Ollama chat failed. Is `ollama serve` running and the model created?"
        ) from exc
    content = response.json().get("message", {}).get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Ollama returned an empty message")
    return content.strip()


def chat_loop(model: str) -> None:
    system = load_system_prompt()
    history = [{"role": "system", "content": system}]
    print("YeatGPT chat. /quit to stop. This is a character simulation, not the artist.")
    while True:
        try:
            user = input("you> ").strip()
        except EOFError:
            print()
            return
        if user in {"/quit", "quit", "exit"}:
            return
        if not user:
            continue
        history.append({"role": "user", "content": user})
        reply = ollama_chat(model, history)
        history.append({"role": "assistant", "content": reply})
        print(reply)


def write_modelfile(gguf) -> None:
    from pathlib import Path

    gguf_path = Path(gguf).expanduser().resolve()
    if not gguf_path.is_file():
        raise FileNotFoundError(f"GGUF not found: {gguf_path}")
    system = load_system_prompt()
    if '"""' in system:
        raise RuntimeError("System prompt cannot contain triple quotes")
    MODELFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"FROM {gguf_path}\n"
        f'SYSTEM """{system}"""\n'
        "PARAMETER temperature 0.7\n"
        "PARAMETER top_p 0.9\n"
        "PARAMETER repeat_penalty 1.1\n"
        "PARAMETER num_ctx 2048\n"
    )
    MODELFILE_PATH.write_text(body, encoding="utf-8")
    print(f"ollama create yeat-gpt -f {MODELFILE_PATH}")


def run_eval(ollama: str | None = None) -> None:
    rows = load_eval_prompts()
    problems = validate_eval_prompts(rows)
    if problems:
        for problem in problems:
            print(problem)
        raise SystemExit(1)
    counts = Counter(str(row.get("category")) for row in rows)
    print(f"{len(rows)} prompts")
    for name in REQUIRED_CATEGORIES:
        print(f"  {name}: {counts[name]}")
    if not ollama:
        print("No backend. Pass --ollama MODEL to generate eval/outputs.jsonl.")
        return
    system = load_system_prompt()
    outputs = []
    for row in rows:
        messages = _with_persona(list(row["messages"]), system)
        text = ollama_chat(ollama, messages)
        outputs.append({"id": row.get("id"), "category": row.get("category"), "output": text})
        print(f"{row.get('id')}: {text[:120]}")
    write_jsonl(EVAL_OUTPUTS_PATH, outputs)
    print(f"Wrote {EVAL_OUTPUTS_PATH}")
