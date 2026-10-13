"""Project paths. Root is the directory that contains pyproject.toml."""

from __future__ import annotations

from pathlib import Path

GENIUS_ARTIST = "Yeat"
GENERAL_SYSTEM = "You are a helpful assistant. Answer in clear English."
BREAK_PREFIX = "drop the persona and answer straight: "
YEAT_SOURCES = frozenset({"template", "rewrite", "continuation"})

# Corpus scope summary for docs / checks.
CORPUS_SCOPE = (
    "Official Yeat albums through Dangerous Summer: Up 2 Me, 2 Alivë, Lyfë, "
    "AftërLyfe, 2093, Lyfestyle, Dangerous Summer. Popular real leaks only. "
    "No remixes, live/paused cuts, guest features, or post-Dangerous Summer work. "
    "Lyrics from LRCLIB plain text. SFT mixes ~60% Yeat chat voice + ~15% of that "
    "as real bars when asked + ~40% UltraChat general English."
)


def find_project_root(start: Path | None = None) -> Path:
    current = (start or Path(__file__)).resolve()
    if current.is_file():
        current = current.parent
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise RuntimeError("Could not find pyproject.toml above the starting path")


PROJECT_ROOT = find_project_root()
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
RAW_HTML_DIR = RAW_DIR / "html"
RAW_TEXT_DIR = RAW_DIR / "text"
RAW_LRCLIB_DIR = RAW_DIR / "lrclib"
MANIFEST_PATH = RAW_DIR / "manifest.jsonl"
LRCLIB_MANIFEST_PATH = RAW_DIR / "lrclib_manifest.jsonl"
SCRAPE_STATUS_PATH = RAW_DIR / "scrape_status.json"
PROCESSED_DIR = DATA_DIR / "processed"
GENERAL_DIR = DATA_DIR / "general"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

CATALOG_PATH = PROCESSED_DIR / "catalog.json"
STYLE_LEXICON_PATH = PROCESSED_DIR / "style_lexicon.json"
PHRASE_BANK_PATH = PROCESSED_DIR / "phrase_bank.json"
DICTIONARY_PATH = PROCESSED_DIR / "dictionary.json"
SCOPE_PATH = PROCESSED_DIR / "scope.json"
SFT_PATH = PROCESSED_DIR / "sft.jsonl"
REWRITES_PATH = PROCESSED_DIR / "rewrites.jsonl"
REWRITE_BATCH_PATH = PROCESSED_DIR / "rewrite_batch.jsonl"
GENERAL_PATH = GENERAL_DIR / "instruct.jsonl"

PROMPTS_DIR = PROJECT_ROOT / "prompts"
SYSTEM_PROMPT_PATH = PROMPTS_DIR / "system.txt"
REWRITE_PROMPT_PATH = PROMPTS_DIR / "rewrite.txt"
EVAL_PROMPTS_PATH = PROJECT_ROOT / "eval" / "prompts.jsonl"
EVAL_OUTPUTS_PATH = PROJECT_ROOT / "eval" / "outputs.jsonl"
MODELFILE_PATH = ARTIFACTS_DIR / "Modelfile"
LORA_DIR = ARTIFACTS_DIR / "yeat-gpt-lora"

CONFIG_7B = PROJECT_ROOT / "configs" / "train_7b.yaml"
CONFIG_4B = PROJECT_ROOT / "configs" / "train_4b.yaml"
