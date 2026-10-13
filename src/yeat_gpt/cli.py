"""Typer CLI for the YeatGPT data pipeline."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="YeatGPT conversational persona pipeline", no_args_is_help=True)


def _fail(message: str) -> None:
    typer.echo(message)
    raise typer.Exit(1)


@app.command("import")
def import_cmd(
    path: Path = typer.Argument(..., help="Pickle, HTML directory, text, JSON/JSONL, or zip"),
):
    """Import lyrics into data/raw without deleting songs already stored."""
    import pickle

    from yeat_gpt.data.importer import import_path

    try:
        stats = import_path(path)
    except (FileNotFoundError, ValueError, pickle.UnpicklingError) as exc:
        _fail(str(exc))
    typer.echo(
        "html_written={html_written} text_written={text_written} "
        "skipped={skipped} failed={failed}".format(**stats)
    )


@app.command()
def scrape(
    album: str | None = typer.Option(
        None, help="Unused for LRCLIB (kept for CLI compatibility)"
    ),
    source: str = typer.Option(
        "lrclib",
        help="Lyric source: lrclib (default) or genius (needs GENIUS token)",
    ),
):
    """Download in-scope Yeat plain lyrics. Default source is LRCLIB (no token)."""
    _ = album  # reserved for future album-key filtering
    try:
        if source == "lrclib":
            from yeat_gpt.scrape.lrclib import run_scrape

            stats = run_scrape()
            typer.echo(
                f"listed={stats['listed']} already_present={stats['already_present']} "
                f"newly_downloaded={stats['newly_downloaded']} missed={stats.get('missed', 0)}"
            )
            return
        if source == "genius":
            from yeat_gpt.scrape.genius import run_scrape as run_genius

            stats = run_genius(album_filter=album)
            typer.echo(
                f"listed={stats['listed']} already_present={stats['already_present']} "
                f"newly_downloaded={stats['newly_downloaded']}"
            )
            return
    except RuntimeError as exc:
        _fail(str(exc))
    _fail("source must be lrclib or genius")


@app.command()
def clean():
    """Parse LRCLIB JSON (and optional HTML/text) into data/processed/catalog.json."""
    from yeat_gpt.clean.lyrics import run_clean

    try:
        stats = run_clean()
    except RuntimeError as exc:
        _fail(str(exc))
    typer.echo(
        f"songs_cleaned={stats['songs_cleaned']} "
        f"from_lrclib={stats.get('from_lrclib', 0)} "
        f"from_html={stats['from_html']} "
        f"from_text={stats['from_text']} "
        f"skipped={stats['skipped']}"
    )


@app.command("fetch-general")
def fetch_general_cmd(count: int = typer.Option(2500, help="Short English pairs to keep")):
    """Download a modest UltraChat mix. Requires: uv sync --extra general."""
    from yeat_gpt.data.general import fetch_general

    try:
        fetch_general(count=count)
    except ModuleNotFoundError as exc:
        _fail(str(exc))
    except RuntimeError as exc:
        _fail(str(exc))


@app.command()
def build(
    templates: int = typer.Option(2000, help="Cap on bootstrap template rows"),
    continuations: float = typer.Option(0.15, help="Continuation share of the yeat portion"),
    rewrite_batch: int = typer.Option(500, help="Rows to queue for a rewrite pass"),
    seed: int = typer.Option(42),
):
    """Build rewrite batch and, when general data exists, data/processed/sft.jsonl."""
    from yeat_gpt.data.sft import build_sft

    try:
        stats = build_sft(
            max_templates=templates,
            continuation_fraction=continuations,
            rewrite_batch=rewrite_batch,
            seed=seed,
        )
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        _fail(str(exc))
    typer.echo(
        f"templates={stats['templates']} rewrites={stats['rewrites']} "
        f"continuations={stats['continuations']} rewrite_batch={stats['rewrite_batch']} "
        f"sft={stats['sft']}"
    )


@app.command("import-rewrites")
def import_rewrites_cmd(path: Path = typer.Argument(..., help="JSONL of {id, assistant}")):
    """Accept rewritten replies, reject verbatim bars, then rebuild."""
    from yeat_gpt.data.rewrite import import_rewrite_file
    from yeat_gpt.data.sft import build_sft

    try:
        stats = import_rewrite_file(path)
        built = build_sft()
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        _fail(str(exc))
    typer.echo(
        f"accepted={stats['accepted']} rejected={stats['rejected']} stored={stats['stored']} "
        f"sft={built['sft']}"
    )


@app.command()
def rewrite():
    """Optional OpenAI-compatible rewrite. Resume-safe. Prints setup help if env is missing."""
    from yeat_gpt.data.rewrite import run_rewrite

    try:
        count = run_rewrite()
    except (FileNotFoundError, RuntimeError) as exc:
        _fail(str(exc))
    typer.echo(f"rewrites_written={count}")


@app.command()
def check():
    """Fail if the SFT mix is missing, yeat-only, or bar-heavy."""
    from yeat_gpt.data.sft import run_check

    problems = run_check()
    if problems:
        for problem in problems:
            typer.echo(problem)
        raise typer.Exit(1)
    typer.echo("check ok")


@app.command()
def train(
    config: Path | None = typer.Option(None, "--config", help="train_7b.yaml or train_4b.yaml"),
    output: Path | None = typer.Option(None, "--output", help="Adapter directory"),
    gguf: bool = typer.Option(False, "--gguf", help="Also write a q4_k_m GGUF"),
    push_to_hub: str | None = typer.Option(None, "--push-to-hub"),
    allow_yeat_only: bool = typer.Option(False, "--allow-yeat-only"),
):
    """Train on Colab or another GPU. Refuses a yeat-only mix unless overridden."""
    from yeat_gpt.train.sft import run_train

    try:
        path = run_train(
            config_path=config,
            output_dir=output,
            gguf=gguf,
            push_to_hub=push_to_hub,
            allow_yeat_only=allow_yeat_only,
        )
    except RuntimeError as exc:
        _fail(str(exc))
    typer.echo(f"adapter={path}")


@app.command()
def chat(
    ollama: str = typer.Option(..., "--ollama", help="Ollama model name, for example yeat-gpt"),
):
    """Local REPL through Ollama. No local GPU required."""
    from yeat_gpt.runtime import chat_loop

    try:
        chat_loop(ollama)
    except RuntimeError as exc:
        _fail(str(exc))


@app.command("export-modelfile")
def export_modelfile_cmd(gguf: Path = typer.Argument(..., help="Path to the exported GGUF")):
    """Write artifacts/Modelfile and print the ollama create command."""
    from yeat_gpt.runtime import write_modelfile

    try:
        write_modelfile(gguf)
    except (FileNotFoundError, RuntimeError) as exc:
        _fail(str(exc))


@app.command("eval")
def eval_cmd(
    ollama: str | None = typer.Option(
        None, "--ollama", help="Run the pack against this Ollama model"
    ),
):
    """Validate eval/prompts.jsonl. With --ollama, write eval/outputs.jsonl."""
    from yeat_gpt.runtime import run_eval

    try:
        run_eval(ollama)
    except (FileNotFoundError, RuntimeError) as exc:
        _fail(str(exc))


if __name__ == "__main__":
    app()
