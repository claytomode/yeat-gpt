import random

from yeat_gpt.config import BREAK_PREFIX, GENERAL_SYSTEM
from yeat_gpt.data.rewrite import accept_rewrite
from yeat_gpt.data.sft import (
    assess_rows,
    build_continuation_rows,
    build_template_rows,
    mix_rows,
    run_check,
)

SONG = {
    "title": "Desk Lamp",
    "text": "\n".join(
        [
            "the blue lamp hums on the desk tonight",
            "I count the quiet cars along the block",
            "a paper cup is warm inside my hand",
            "the hallway light clicks off behind the door",
        ]
    ),
}
LINES = [line.strip() for line in SONG["text"].splitlines()]


def test_template_reply_has_english_lead():
    rows = build_template_rows([SONG], limit=12, rng=random.Random(0), system="persona")
    assert rows
    for row in rows:
        assistant = row["messages"][2]["content"]
        first = assistant.splitlines()[0]
        assert assistant.strip() not in LINES
        assert first not in LINES
        assert first.startswith(("I ", "Yeah "))
        assert "." in first
        assert " " in first


def test_continuation_asks_for_real_lines():
    rows = build_continuation_rows([SONG], limit=8, rng=random.Random(1), system="persona")
    assert rows
    for row in rows:
        user = row["messages"][1]["content"].lower()
        assert any(token in user for token in ("bar", "verse", "line"))
        content = row["messages"][2]["content"]
        spoken = [line.strip() for line in content.splitlines() if line.strip()]
        assert 2 <= len(spoken) <= 4
        for line in spoken:
            assert line in SONG["text"]


def test_rewrite_rejects_verbatim_bars():
    bars = ["the blue lamp hums on the desk tonight"]
    assert accept_rewrite("", bars)[0] is False
    assert accept_rewrite("too short", bars)[0] is False
    assert accept_rewrite(bars[0], bars)[0] is False
    ok, reason = accept_rewrite("I like how quiet the room gets after midnight.", bars)
    assert ok, reason


def test_mix_ratio_includes_general_and_break():
    yeat = [
        {
            "source": "template",
            "messages": [
                {"role": "system", "content": "persona"},
                {"role": "user", "content": f"hey {index}"},
                {"role": "assistant", "content": "I am good. Just been moving through the day."},
            ],
        }
        for index in range(30)
    ]
    general = [
        {"user": f"What is item {index}?", "assistant": f"Item {index} is a plain English answer."}
        for index in range(100)
    ]
    mixed = mix_rows(yeat, general, rng=random.Random(42), persona="persona")
    sources = {row["source"] for row in mixed}
    assert "general" in sources
    assert "break" in sources
    yeat_n = sum(1 for row in mixed if row["source"] == "template")
    assert abs(yeat_n / len(mixed) - 0.6) < 0.05
    break_rows = [row for row in mixed if row["source"] == "break"]
    assert break_rows
    assert break_rows[0]["messages"][1]["content"].startswith(BREAK_PREFIX)
    assert break_rows[0]["messages"][0]["content"] == "persona"
    general_rows = [row for row in mixed if row["source"] == "general"]
    assert general_rows[0]["messages"][0]["content"] == GENERAL_SYSTEM


def test_check_rejects_yeat_only_rows(tmp_path):
    rows = [
        {
            "source": "template",
            "messages": [
                {"role": "system", "content": "persona"},
                {"role": "user", "content": "how are you doing"},
                {"role": "assistant", "content": "I am good. Just been moving through the day."},
            ],
        }
    ]
    problems = assess_rows(rows, corpus_lines=LINES)
    assert any("general" in problem for problem in problems)
    missing = run_check(tmp_path / "sft.jsonl", tmp_path / "catalog.json")
    assert any("missing" in problem for problem in missing)
