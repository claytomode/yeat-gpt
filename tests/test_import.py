import pickle
from dataclasses import dataclass

from yeat_gpt.data.importer import import_path


@dataclass
class Song:
    title: str
    url: str
    id: int


def test_pickle_remaps_foreign_song(tmp_path):
    song = Song("Desk Lamp", "https://example.test/songs/42", 42)
    html = "<html><title>Desk Lamp</title><body>hello from html</body></html>"
    payload = pickle.dumps([{"song": song, "html": html}])
    module = Song.__module__.encode()
    payload = payload.replace(module, b"x" * len(module))
    payload_path = tmp_path / "yeat_raw_html_progress.pkl"
    payload_path.write_bytes(payload)
    with payload_path.open("rb") as handle:
        try:
            pickle.load(handle)
            raised = False
        except ModuleNotFoundError:
            raised = True
    assert raised
    html_dir = tmp_path / "html"
    stats = import_path(
        payload_path,
        html_dir=html_dir,
        text_dir=tmp_path / "text",
        manifest_path=tmp_path / "manifest.jsonl",
    )
    written = html_dir / "42.html"
    assert stats["html_written"] == 1
    assert "hello from html" in written.read_text(encoding="utf-8")


def test_txt_and_jsonl_import(tmp_path):
    text_path = tmp_path / "lyrics.txt"
    text_path.write_text(
        "alpha line one\n\n<|endoftext|>\n\nbeta line two\n",
        encoding="utf-8",
    )
    text_dir = tmp_path / "text"
    stats = import_path(
        text_path,
        html_dir=tmp_path / "html",
        text_dir=text_dir,
        manifest_path=tmp_path / "manifest.jsonl",
    )
    blob = "\n".join(path.read_text(encoding="utf-8") for path in text_dir.glob("*.txt"))
    assert stats["text_written"] == 2
    assert "alpha line one" in blob
    assert "beta line two" in blob

    jsonl_path = tmp_path / "songs.jsonl"
    jsonl_path.write_text(
        '{"title": "One", "text": "hello from jsonl"}\n'
        '{"title": "Two", "lyrics": "second song line"}\n',
        encoding="utf-8",
    )
    json_dir = tmp_path / "json-text"
    import_path(
        jsonl_path,
        html_dir=tmp_path / "html2",
        text_dir=json_dir,
        manifest_path=tmp_path / "manifest2.jsonl",
    )
    blob = "\n".join(path.read_text(encoding="utf-8") for path in json_dir.glob("*.txt"))
    assert "hello from jsonl" in blob
    assert "second song line" in blob
