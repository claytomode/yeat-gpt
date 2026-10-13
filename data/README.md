# Data drop folder

`yeat-gpt import PATH` accepts:

- A v1 pickle named like `yeat_raw_html_progress.pkl`. It was saved from a notebook as a `Song` dataclass (`title`, `url`, `id`) plus `html`. The importer remaps that class and writes `data/raw/html/{id}.html`.
- A directory of Genius HTML files.
- A text file split on `<|endoftext|>`.
- JSON or JSONL objects with `title` and `text` or `lyrics`.
- A zip of any of the above.

That import is an older snapshot, not the full discography. `uv run yeat-gpt scrape` downloads songs whose Genius ids are not already in `data/raw/html` and does not delete imported files. `clean` then merges both into `data/processed/catalog.json`.

Do not commit raw HTML, the catalog, `sft.jsonl`, or lyric text. Those paths are gitignored.
