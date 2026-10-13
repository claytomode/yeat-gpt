from yeat_gpt.clean.lyrics import clean_raw_text, process_lyrics_with_styles


def test_clean_raw_strips_brackets_and_keeps_parentheticals():
    text = "[Verse: Yeat]\nline one\n(yeah)\nRead More junk"
    lines = clean_raw_text(text)
    assert any("line one" in line for line in lines)
    assert any("(yeah)" in line for line in lines)
    assert all("[" not in line and "]" not in line for line in lines)
    assert all("Read More" not in line for line in lines)


def test_skip_non_yeat_header():
    from lxml import html

    fragment = """
    <motionless><div data-lyrics-container="true">
    [Verse: Other Artist: bold]their line
    [Verse: Yeat]my line
    </div></motionless>
    """
    tree = html.fromstring(fragment)
    containers = tree.xpath('//div[@data-lyrics-container="true"]')
    raw = process_lyrics_with_styles(containers)
    assert "my line" in raw
    assert "their line" not in raw
