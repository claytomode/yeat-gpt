# Data drop folder

## Primary path (LRCLIB)

```text
uv run yeat-gpt scrape    # writes data/raw/lrclib/{id}.json
uv run yeat-gpt clean     # catalog + dictionary + scope.json
uv run yeat-gpt fetch-general
uv run yeat-gpt build     # data/processed/sft.jsonl
uv run yeat-gpt check
```

Scope is fixed in code (`yeat_gpt.scrape.scope`):

- Official albums through **Dangerous Summer**
- A short allowlist of popular real leaks
- No remixes, live/paused cuts, features, or newer projects

## Optional imports

`yeat-gpt import PATH` still accepts older snapshots:

- A v1 pickle named like `yeat_raw_html_progress.pkl`
- A directory of Genius HTML files
- A text file split on `<|endoftext|>`
- JSON or JSONL objects with `title` and `text` or `lyrics`
- A zip of any of the above

`clean` prefers LRCLIB rows and dedupes by title against any HTML/text imports.

## Do not commit

Raw lyrics, the catalog, `sft.jsonl`, dictionaries mined from lyrics, and `.env` stay gitignored.
