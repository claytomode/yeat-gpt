# YeatGPT

**Content warning:** explicit language. This is a character simulation of Yeat, not the real artist.

You open a chat, talk in normal English, and the reply should sound like him without collapsing into broken lyric autocomplete. Personal research project. Training data is conversational English in that voice, mixed with ordinary instruct data, plus a small share of real lines only when the user asks for bars.

The near-prod model is **Qwen2.5-7B-Instruct** when the GPU has at least 16GB (Colab L4, A100, or a 24GB rental). A free T4 uses **Qwen3-4B-Instruct-2507**. Both are QLoRA in `notebooks/train_colab.ipynb`. Do not train on yeat-only data.

Import covers the lyric snapshot you already have. `uv run yeat-gpt scrape` adds songs that are not in the corpus yet.

## When you get back

The code is committed on this machine and has not been pushed. Lyrics and the Genius token stay untracked.

The pickle import loaded 655 songs. `yeat-gpt check` passed on a local `data/processed/sft.jsonl` built from that snapshot plus UltraChat. That file is gitignored. Genius listed more songs than the pickle contains, and `uv run yeat-gpt scrape` was still downloading the missing ones. Leave it running. When it exits, merge them before you spend Colab units:

```powershell
uv run yeat-gpt clean
uv run yeat-gpt build
uv run yeat-gpt check
```

1. Push this repo when you want it on GitHub.
2. On Colab, pick an **L4 or A100** runtime. Clone the repo, upload `data/processed/sft.jsonl`, and run `notebooks/train_colab.ipynb`. Do not spend the $10 / 100 units until that check passed on the file you upload.
3. After a GGUF export: `uv run yeat-gpt export-modelfile PATH` then the printed `ollama create yeat-gpt -f artifacts/Modelfile`.
4. Chat locally, no GPU required if Ollama is installed: `uv run yeat-gpt chat --ollama yeat-gpt`.
5. Private checklist before you trust it: plain English, the voice, bars only when asked, it drops the persona when asked, and it stays stable for about 10 turns. No public side-by-side page.

The frozen GPT-2 notebook is in [`v1/yeat_gpt.ipynb`](v1/yeat_gpt.ipynb).

## Local pipeline

```powershell
uv sync
uv sync --extra general
uv run yeat-gpt import PATH
uv run yeat-gpt scrape
uv run yeat-gpt clean
uv run yeat-gpt fetch-general
uv run yeat-gpt build
uv run yeat-gpt check
```

Copy `.env.example` to `.env` for the Genius token. Optional rewrite pass before the real train: see `prompts/rewrite.txt`, then `uv run yeat-gpt rewrite` or `uv run yeat-gpt import-rewrites PATH`, then `build` again. Drop formats are in [`data/README.md`](data/README.md).

`check` refuses a yeat-only mix. `build` will not write `sft.jsonl` until general instruct data is present.
