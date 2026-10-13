"""QLoRA SFT. Unsloth is imported inside run_train so data prep never loads torch."""

from __future__ import annotations

import inspect
from pathlib import Path

import yaml

from yeat_gpt.config import CONFIG_4B, CONFIG_7B, LORA_DIR, PROJECT_ROOT, SFT_PATH
from yeat_gpt.jsonl import read_jsonl


def select_config(vram_gb: float, root: Path | None = None) -> Path:
    base = root or PROJECT_ROOT
    if vram_gb >= 16:
        return base / "configs" / "train_7b.yaml"
    return base / "configs" / "train_4b.yaml"


def gpu_report() -> tuple[str, float]:
    import torch

    if not torch.cuda.is_available():
        return "cpu", 0.0
    name = torch.cuda.get_device_name(0)
    memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
    return name, float(memory)


def _explicit_params(fn) -> set[str]:
    return {
        name
        for name, param in inspect.signature(fn).parameters.items()
        if param.kind not in (param.VAR_POSITIONAL, param.VAR_KEYWORD)
    }


def _apply_template(tokenizer, messages: list[dict]) -> str:
    kwargs = {"tokenize": False, "add_generation_prompt": False}
    try:
        return tokenizer.apply_chat_template(messages, enable_thinking=False, **kwargs)
    except TypeError:
        return tokenizer.apply_chat_template(messages, **kwargs)


def _load_config(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Missing train config: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not data.get("base_model"):
        raise ValueError(f"{path} needs a base_model")
    return data


def export_gguf(output_dir: Path) -> None:
    """Called only when the caller already holds an Unsloth model. Prefer run_train(gguf=True)."""
    raise RuntimeError(
        "Pass gguf=True to run_train so the in-memory model can write q4_k_m. "
        f"Adapter dir: {output_dir}"
    )


def run_train(
    *,
    config_path: Path | None = None,
    output_dir: Path | None = None,
    gguf: bool = False,
    push_to_hub: str | None = None,
    allow_yeat_only: bool = False,
    sft_path: Path | None = None,
) -> Path:
    # Unsloth must be imported before torch, trl, or transformers.
    try:
        import unsloth  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Training needs Unsloth on a GPU. Open notebooks/train_colab.ipynb."
        ) from exc

    from yeat_gpt.data.sft import run_check

    if not allow_yeat_only:
        problems = run_check(sft_path)
        if problems:
            raise RuntimeError("Refusing to train:\n" + "\n".join(problems))

    if config_path is None:
        _name, vram = gpu_report()
        config_path = select_config(vram)
        if vram >= 16:
            print(f"GPU {_name} {vram:.1f} GB: using 7B because memory is at least 16GB.")
        else:
            print(f"GPU {_name} {vram:.1f} GB: using 4B because memory is under 16GB.")
    cfg = _load_config(config_path)
    output = output_dir or LORA_DIR
    output.mkdir(parents=True, exist_ok=True)
    data_path = sft_path or SFT_PATH
    rows = read_jsonl(data_path)
    if len(rows) < 8:
        raise RuntimeError(f"{data_path} does not have enough rows to train")

    import torch
    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer
    from unsloth import FastLanguageModel

    max_seq = int(cfg.get("max_seq_length", 2048))
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(cfg["base_model"]),
        max_seq_length=max_seq,
        load_in_4bit=True,
        dtype=None,
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=int(cfg.get("lora_r", 32)),
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        lora_alpha=int(cfg.get("lora_alpha", 32)),
        lora_dropout=float(cfg.get("lora_dropout", 0)),
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    texts = [_apply_template(tokenizer, row["messages"]) for row in rows]
    print(texts[0][:800])
    table = Dataset.from_dict({"text": texts, "source": [row.get("source", "") for row in rows]})
    eval_dataset = None
    if len(table) >= 50:
        split = table.train_test_split(test_size=0.02, seed=42)
        train_dataset = split["train"]
        eval_dataset = split["test"]
    else:
        train_dataset = table

    sft_names = _explicit_params(SFTConfig.__init__)
    sft_kwargs: dict = {
        "output_dir": str(output),
        "per_device_train_batch_size": int(cfg.get("per_device_batch_size", 1)),
        "gradient_accumulation_steps": int(cfg.get("gradient_accumulation_steps", 8)),
        "num_train_epochs": float(cfg.get("epochs", 1)),
        "learning_rate": float(cfg.get("learning_rate", 1e-4)),
        "optim": str(cfg.get("optim", "adamw_8bit")),
        "lr_scheduler_type": str(cfg.get("lr_scheduler_type", "cosine")),
        "warmup_ratio": float(cfg.get("warmup_ratio", 0.05)),
        "logging_steps": 10,
        "seed": 42,
        "dataset_text_field": "text",
        "packing": bool(cfg.get("packing", False)),
    }
    if torch.cuda.is_available() and hasattr(torch.cuda, "is_bf16_supported"):
        if torch.cuda.is_bf16_supported():
            sft_kwargs["bf16"] = True
        else:
            sft_kwargs["fp16"] = True
    if eval_dataset is not None:
        if "eval_strategy" in sft_names:
            sft_kwargs["eval_strategy"] = "epoch"
        elif "evaluation_strategy" in sft_names:
            sft_kwargs["evaluation_strategy"] = "epoch"
    length_key = "max_length" if "max_length" in sft_names else "max_seq_length"
    if length_key in sft_names:
        sft_kwargs[length_key] = max_seq
    filtered = {
        key: value
        for key, value in sft_kwargs.items()
        if key in sft_names or key == length_key
    }
    try:
        args = SFTConfig(**filtered)
    except TypeError:
        filtered.pop(length_key, None)
        other = "max_seq_length" if length_key == "max_length" else "max_length"
        filtered[other] = max_seq
        args = SFTConfig(**filtered)

    trainer_names = _explicit_params(SFTTrainer.__init__)
    trainer_kwargs = {
        "model": model,
        "args": args,
        "train_dataset": train_dataset,
    }
    if eval_dataset is not None and "eval_dataset" in trainer_names:
        trainer_kwargs["eval_dataset"] = eval_dataset
    if "processing_class" in trainer_names:
        trainer_kwargs["processing_class"] = tokenizer
    elif "tokenizer" in trainer_names:
        trainer_kwargs["tokenizer"] = tokenizer
    trainer = SFTTrainer(**trainer_kwargs)
    from unsloth.chat_templates import train_on_responses_only

    trainer = train_on_responses_only(
        trainer,
        instruction_part="<|im_start|>user\n",
        response_part="<|im_start|>assistant\n",
    )
    trainer.train()
    model.save_pretrained(str(output))
    tokenizer.save_pretrained(str(output))
    if gguf:
        model.save_pretrained_gguf(str(output), tokenizer, quantization_method="q4_k_m")
    if push_to_hub:
        model.push_to_hub(push_to_hub)
        tokenizer.push_to_hub(push_to_hub)
    return output


def describe_choice(vram_gb: float) -> str:
    if vram_gb >= 16:
        return (
            f"Using {CONFIG_7B.name}: GPU memory is at least 16GB, "
            "so the near-prod model is Qwen2.5-7B-Instruct."
        )
    return (
        f"Using {CONFIG_4B.name}: GPU memory is under 16GB, "
        "so the fallback is Qwen3-4B-Instruct-2507."
    )
