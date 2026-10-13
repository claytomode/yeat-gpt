# YeatGPT

**Content warning:** explicit language. This is a character simulation of Yeat, not the real artist.

You open a chat, talk in normal English, and the reply should sound like him without collapsing into broken lyric autocomplete. Personal research project. Training data is conversational English in that voice, mixed with ordinary instruct data, plus a small share of real lines only when the user asks for bars.

The near-prod model is **Qwen2.5-7B-Instruct** when the GPU has at least 16GB (Colab L4, A100, or a 24GB rental). A free T4 uses **Qwen3-4B-Instruct-2507**. Both are QLoRA in `notebooks/train_colab.ipynb`. Do not train on yeat-only data.

## Corpus scope

Lyrics come from **LRCLIB plain text** (no Genius token). Scope is intentional and narrow:

- **Official:** Up 2 Me, 2 Alivë (+ Geëk Pack solo cuts), Lyfë, AftërLyfe, 2093, Lyfestyle, Dangerous Summer (if LRCLIB has it)
- **Leaks:** only a few real, popular early cuts (for example Sorry Bout That) — not a dump of every unreleased file
- **Dropped:** remixes, live/paused/sped-up cuts, guest features, anything newer than Dangerous Summer

After `clean`, see `data/processed/scope.json` and `data/processed/dictionary.json` for the exact song list, slang dictionary, and spelling rules.

**Spelling rule (verified):** mark `e` as `ë` on content words (`alivë`, `monëy`). Other vowels (`ä`/`ö`/`ü`/`ï`) appear in branding sometimes but are rarer — prefer `ë` in chat. Never stylize function words (`the`, `I`, `you`). At most two stylized words per reply.

## Local pipeline

```powershell
uv sync
uv sync --extra general
uv run yeat-gpt scrape
uv run yeat-gpt clean
uv run yeat-gpt fetch-general
uv run yeat-gpt build
uv run yeat-gpt check
```

`scrape` defaults to LRCLIB. Genius remains available as `uv run yeat-gpt scrape --source genius` if you set `GENIUS_CLIENT_ACCESS_TOKEN` in `.env`, but it is not required.

SFT mix target: about **60%** Yeat chat voice, about **15%** of the yeat side as real bars when asked, about **40%** UltraChat general English. `check` refuses a yeat-only mix. `build` will not write `sft.jsonl` until general instruct data is present.

Do not commit raw lyrics, `data/processed/sft.jsonl`, or `.env` — those paths are gitignored.

## Train / chat

1. On Colab, pick an **L4 or A100** runtime. Clone the repo, upload `data/processed/sft.jsonl`, and run `notebooks/train_colab.ipynb`.
2. After a GGUF export: `uv run yeat-gpt export-modelfile PATH` then the printed `ollama create yeat-gpt -f artifacts/Modelfile`.
3. Chat locally: `uv run yeat-gpt chat --ollama yeat-gpt`.
4. Private checklist before you trust it: plain English, the voice, bars only when asked, it drops the persona when asked, and it stays stable for about 10 turns.

Optional rewrite pass: see `prompts/rewrite.txt`, then `uv run yeat-gpt rewrite` or `uv run yeat-gpt import-rewrites PATH`, then `build` again.

The frozen GPT-2 notebook is in [`v1/yeat_gpt.ipynb`](v1/yeat_gpt.ipynb).
