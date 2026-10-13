from yeat_gpt.clean.voice import apply_voice_spelling, is_function_word, stylize_content_word
from yeat_gpt.scrape.scope import (
    is_dropped_title,
    match_official_album,
    score_candidate,
    track_matches,
)


def test_drop_remix_live_feature_titles():
    assert is_dropped_title("Monëy so big (Remix)")
    assert is_dropped_title("Poppin (Live)")
    assert is_dropped_title("Outsidë (feat. Young Thug)")
    assert is_dropped_title("Lyfestylë (with Lil Wayne)")
    assert not is_dropped_title("Monëy so big")
    assert not is_dropped_title("Poppin")


def test_official_album_match():
    assert match_official_album("Up 2 Më") == "up_2_me"
    assert match_official_album("2 Alivë (Geëk Pack)") == "2_alive"
    assert match_official_album("DANGEROUS SUMMER") == "dangerous_summer"
    assert match_official_album("Random Leak Dump") is None


def test_score_prefers_matching_album():
    job = {
        "kind": "official",
        "album_key": "2_alive",
        "album_label": "2 Alivë",
        "title": "Poppin",
    }
    good = {
        "artistName": "Yeat",
        "trackName": "Poppin",
        "albumName": "2 Alivë",
        "plainLyrics": "line\n" * 40,
        "instrumental": False,
    }
    bad = {
        "artistName": "Other feat. Yeat",
        "trackName": "Poppin",
        "albumName": "2 Alivë",
        "plainLyrics": "line\n" * 40,
        "instrumental": False,
    }
    assert score_candidate(job, good) > 0
    assert score_candidate(job, bad) < 0
    assert track_matches("Poppin", "Poppin")


def test_spelling_skips_function_words_and_caps_at_two():
    assert is_function_word("the")
    assert is_function_word("I")
    assert stylize_content_word("the") is None
    assert stylize_content_word("alive") == "alivë"
    styled = apply_voice_spelling(
        "I keep the lyfe money alive forever tonight everywhere",
        max_stylized=2,
    )
    diacritic_words = [w for w in styled.split() if any(ord(c) > 127 for c in w)]
    assert len(diacritic_words) <= 2
    assert "thë" not in styled.casefold()
    assert "herë" not in styled.casefold()
    assert styled.startswith("I ")
    # Ordinary English should not get random umlauts.
    plain = apply_voice_spelling("Yeah I am here. Moving quiet and staying tun.")
    assert "herë" not in plain
    assert "quiët" not in plain
