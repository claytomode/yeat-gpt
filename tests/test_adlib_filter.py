from yeat_gpt.clean.adlibs import filter_lines, is_adlib_only_line


def test_adlib_only_dropped():
    assert is_adlib_only_line("yeah")
    assert is_adlib_only_line("what?")
    lines, stats = filter_lines(["yeah", "pulled up in that tonka", "what what"], for_verse=True)
    assert "tonka" in lines[0]
    assert stats["dropped_adlib"] >= 2


def test_keeps_coded_words():
    lines, _ = filter_lines(["tonka truck big body", "percs in my system"], for_verse=True)
    assert len(lines) == 2
