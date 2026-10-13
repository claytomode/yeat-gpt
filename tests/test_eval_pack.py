from yeat_gpt.runtime import REQUIRED_CATEGORIES, load_eval_prompts, validate_eval_prompts


def test_eval_pack_covers_required_categories():
    rows = load_eval_prompts()
    assert 18 <= len(rows) <= 24
    categories = {row["category"] for row in rows}
    for name in REQUIRED_CATEGORIES:
        assert name in categories
    assert validate_eval_prompts(rows) == []
