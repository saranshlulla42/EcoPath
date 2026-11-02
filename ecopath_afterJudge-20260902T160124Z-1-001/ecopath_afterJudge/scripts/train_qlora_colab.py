"""
Colab-friendly QLoRA training script for extinction-risk report drafting.

Design goals:
- Run in Google Colab free tier first, with optional Pro upgrades if needed.
- Use a 4-bit quantized base model plus LoRA adapters.
- Save checkpoints and artifacts to Google Drive so the run survives disconnects.
- Keep the training data contract aligned with generate_synthetic_dataset.py.
- Be explicit about all assumptions and paths so the notebook can be copied
  into Colab without requiring repo-specific edits.

Recommended base models:
- Qwen/Qwen2.5-7B-Instruct
- meta-llama/Llama-3.1-8B-Instruct

The script intentionally avoids hard-coding one base model. Set --model_name
from the command line or in a Colab cell before execution.
"""

from __future__ import annotations

import argparse
import inspect
import json
import math
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import torch
from datasets import Dataset
from huggingface_hub import login
from peft import LoraConfig, PeftModel, TaskType, get_peft_model, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    DataCollatorForLanguageModeling,
    Trainer,
    TrainingArguments,
)


# ---------------------------------------------------------------------------
# Config / helpers
# ---------------------------------------------------------------------------

DEFAULT_SYSTEM_PROMPT = (
    "You are a conservation science assistant drafting a decision-support report "
    "for human experts. Use the provided species profile and evidence only. "
    "Do not invent statistics. State uncertainty clearly. Return a structured "
    "report with inline evidence and a reviewer-facing disclaimer."
)


@dataclass
class TrainConfig:
    train_jsonl: str
    model_name: str
    output_dir: str
    drive_root: str
    run_name: str
    max_seq_length: int = 4096
    per_device_train_batch_size: int = 1
    gradient_accumulation_steps: int = 8
    learning_rate: float = 2e-4
    num_train_epochs: float = 3.0
    warmup_ratio: float = 0.03
    logging_steps: int = 10
    save_steps: int = 100
    eval_steps: int = 100
    # This is the final held-out test set. With the 100-record Gemini teacher
    # dataset, the default produces 85 training and 15 evaluation records.
    eval_split_ratio: float = 0.15
    split_output_dir: Optional[str] = None
    resume_from_checkpoint: Optional[str] = None
    seed: int = 42
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    target_modules: str = "q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj"
    bf16: bool = True
    gradient_checkpointing: bool = True
    push_to_hub: bool = False
    hub_model_id: Optional[str] = None
    hub_token: Optional[str] = None


def _ensure_dir(path: str | Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def split_dataset(rows: list[dict[str, Any]], eval_split_ratio: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not rows:
        raise ValueError("Training data is empty.")
    if not 0 < eval_split_ratio < 1:
        raise ValueError("eval_split_ratio must be greater than 0 and less than 1.")

    rng = random.Random(seed)
    shuffled = rows[:]
    rng.shuffle(shuffled)
    eval_size = max(1, round(len(shuffled) * eval_split_ratio)
                    ) if len(shuffled) > 1 else 0
    eval_rows = shuffled[:eval_size]
    train_rows = shuffled[eval_size:] if eval_size else shuffled
    return train_rows, eval_rows


def write_split_files(train_rows: list[dict[str, Any]], eval_rows: list[dict[str, Any]], split_dir: Path, seed: int, eval_split_ratio: float) -> dict[str, Path]:
    split_dir.mkdir(parents=True, exist_ok=True)

    train_path = split_dir / "train.jsonl"
    eval_path = split_dir / "eval.jsonl"
    manifest_path = split_dir / "manifest.json"

    with train_path.open("w", encoding="utf-8") as handle:
        for row in train_rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")

    with eval_path.open("w", encoding="utf-8") as handle:
        for row in eval_rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")

    manifest = {
        "seed": seed,
        "heldout_eval_ratio": eval_split_ratio,
        "train_examples": len(train_rows),
        "eval_examples": len(eval_rows),
        "eval_usage": "final base-vs-fine-tuned comparison only; never used during training",
        "train_jsonl": str(train_path),
        "eval_jsonl": str(eval_path),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    return {
        "train_jsonl": train_path,
        "eval_jsonl": eval_path,
        "manifest_json": manifest_path,
    }


def format_example(example: dict[str, Any]) -> str:
    """
    Convert one dataset row into a chat-style training sample.

    The dataset generator stores:
    - input: structured species/profile/task payload
    - search_queries: list[str]
    - search_results: list[EvidenceItem dicts]
    - output: teacher draft

    We present the model with a realistic instruction prompt and ask it to
    generate the final report body.
    """
    species_block = json.dumps(example["input"], ensure_ascii=True, indent=2)
    queries_block = json.dumps(example.get(
        "search_queries", []), ensure_ascii=True, indent=2)
    results_block = json.dumps(example.get(
        "search_results", []), ensure_ascii=True, indent=2)
    output_block = example.get("output", "").strip()

    user_prompt = (
        "Use the retrieved evidence to draft a decision-support report for human conservation experts.\n\n"
        f"SPECIES INPUT:\n{species_block}\n\n"
        f"SEARCH QUERIES:\n{queries_block}\n\n"
        f"SEARCH RESULTS:\n{results_block}\n\n"
        "Requirements:\n"
        "- Structure the response as a decision-support draft, not a verdict.\n"
        "- Include current conservation status, key threats, risk reasoning, mitigation actions, and sources.\n"
        "- Use IUCN-style reasoning when you discuss decline or range contraction.\n"
        "- Do not fabricate statistics.\n"
        "- Keep citations inline and human-verifiable.\n"
    )

    system_prompt = DEFAULT_SYSTEM_PROMPT
    assistant_prompt = output_block if output_block else ""

    return (
        f"<|system|>\n{system_prompt}\n<|end|>\n"
        f"<|user|>\n{user_prompt}\n<|end|>\n"
        f"<|assistant|>\n{assistant_prompt}"
    )


def build_tokenizer(model_name: str):
    tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    return tokenizer


def build_model(model_name: str, bf16: bool):
    compute_dtype = torch.bfloat16 if bf16 and torch.cuda.is_available() else torch.float16
    quant_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=compute_dtype,
    )

    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        quantization_config=quant_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model = prepare_model_for_kbit_training(model)
    return model


def build_lora_config(cfg: TrainConfig) -> LoraConfig:
    target_modules = [part.strip()
                      for part in cfg.target_modules.split(",") if part.strip()]
    return LoraConfig(
        r=cfg.lora_r,
        lora_alpha=cfg.lora_alpha,
        lora_dropout=cfg.lora_dropout,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        target_modules=target_modules,
    )


def tokenize_dataset(rows: list[dict[str, Any]], tokenizer, max_seq_length: int) -> Dataset:
    formatted = [{"text": format_example(row)} for row in rows]
    dataset = Dataset.from_list(formatted)

    def tokenize(batch: dict[str, list[str]]) -> dict[str, Any]:
        return tokenizer(
            batch["text"],
            truncation=True,
            max_length=max_seq_length,
            padding=False,
        )

    tokenized = dataset.map(tokenize, batched=True, remove_columns=["text"])
    tokenized = tokenized.map(lambda _: {"labels": _.get("input_ids", [])})
    return tokenized


def collator(tokenizer):
    return DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)


def prepare_output_paths(cfg: TrainConfig) -> dict[str, Path]:
    drive_root = _ensure_dir(cfg.drive_root)
    run_root = _ensure_dir(drive_root / "ecopath" /
                           "extinction_risk" / cfg.run_name)
    output_dir = _ensure_dir(run_root / "checkpoints")
    final_dir = _ensure_dir(run_root / "final")
    logs_dir = _ensure_dir(run_root / "logs")
    split_dir = _ensure_dir(
        cfg.split_output_dir) if cfg.split_output_dir else _ensure_dir(run_root / "splits")
    return {"run_root": run_root, "output_dir": output_dir, "final_dir": final_dir, "logs_dir": logs_dir, "splits_dir": split_dir}


def maybe_login_to_hub(token: Optional[str]) -> None:
    if token:
        login(token=token)


def train(cfg: TrainConfig) -> dict[str, Any]:
    random.seed(cfg.seed)
    torch.manual_seed(cfg.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(cfg.seed)

    paths = prepare_output_paths(cfg)
    maybe_login_to_hub(cfg.hub_token)

    rows = load_jsonl(cfg.train_jsonl)
    train_rows, eval_rows = split_dataset(rows, cfg.eval_split_ratio, cfg.seed)

    split_files = write_split_files(
        train_rows,
        eval_rows,
        paths["splits_dir"],
        seed=cfg.seed,
        eval_split_ratio=cfg.eval_split_ratio,
    )
    print(f"Saved {len(train_rows)} training and {len(eval_rows)} held-out evaluation records to {paths['splits_dir']}")

    tokenizer = build_tokenizer(cfg.model_name)
    model = build_model(cfg.model_name, cfg.bf16)
    model = get_peft_model(model, build_lora_config(cfg))

    if cfg.gradient_checkpointing:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False

    train_ds = tokenize_dataset(train_rows, tokenizer, cfg.max_seq_length)
    data_collator = collator(tokenizer)

    train_args_kwargs: dict[str, Any] = {
        "output_dir": str(paths["output_dir"]),
        "run_name": cfg.run_name,
        "per_device_train_batch_size": cfg.per_device_train_batch_size,
        "per_device_eval_batch_size": cfg.per_device_train_batch_size,
        "gradient_accumulation_steps": cfg.gradient_accumulation_steps,
        "learning_rate": cfg.learning_rate,
        "num_train_epochs": cfg.num_train_epochs,
        "logging_steps": cfg.logging_steps,
        "save_steps": cfg.save_steps,
        "save_total_limit": 3,
        "save_strategy": "steps",
        "bf16": cfg.bf16 and torch.cuda.is_available(),
        "fp16": not (cfg.bf16 and torch.cuda.is_available()),
        "report_to": "none",
        "logging_dir": str(paths["logs_dir"]),
        "remove_unused_columns": False,
        # Do not use the 15% final evaluation split to select checkpoints.
        "load_best_model_at_end": False,
    }

    training_args_params = inspect.signature(TrainingArguments).parameters
    # Some Colab images ship an older Transformers release that only accepts
    # warmup_steps. Preserve the requested warmup amount on both APIs.
    if "warmup_ratio" in training_args_params:
        train_args_kwargs["warmup_ratio"] = cfg.warmup_ratio
    elif "warmup_steps" in training_args_params:
        updates_per_epoch = math.ceil(
            len(train_ds) / max(1, cfg.per_device_train_batch_size * cfg.gradient_accumulation_steps)
        )
        estimated_total_updates = updates_per_epoch * math.ceil(cfg.num_train_epochs)
        train_args_kwargs["warmup_steps"] = round(
            estimated_total_updates * cfg.warmup_ratio
        )
        print(
            "Installed Transformers does not support warmup_ratio; "
            f"using {train_args_kwargs['warmup_steps']} warmup step(s) instead."
        )
    if "eval_strategy" in training_args_params:
        train_args_kwargs["eval_strategy"] = "no"
    else:
        train_args_kwargs["evaluation_strategy"] = "no"

    # Colab can provide an older TrainingArguments API even after installing
    # dependencies. Keep the portable core settings and drop only optional
    # arguments absent from that installed version.
    unsupported_args = sorted(
        set(train_args_kwargs) - set(training_args_params)
    )
    if unsupported_args:
        print(
            "Installed Transformers does not support optional TrainingArguments: "
            + ", ".join(unsupported_args)
            + ". Continuing without them."
        )
        train_args_kwargs = {
            key: value
            for key, value in train_args_kwargs.items()
            if key in training_args_params
        }

    train_args = TrainingArguments(**train_args_kwargs)

    trainer = Trainer(
        model=model,
        args=train_args,
        train_dataset=train_ds,
        eval_dataset=None,
        data_collator=data_collator,
    )

    trainer.train(resume_from_checkpoint=cfg.resume_from_checkpoint)

    # Save adapters and tokenizer to Drive so they survive disconnects.
    trainer.save_model(str(paths["final_dir"]))
    tokenizer.save_pretrained(str(paths["final_dir"]))

    metrics = {"heldout_eval_reserved": len(eval_rows)}
    (paths["run_root"] / "metrics.json").write_text(json.dumps(metrics,
                                                               indent=2), encoding="utf-8")

    if cfg.push_to_hub and cfg.hub_model_id:
        trainer.push_to_hub(cfg.hub_model_id)

    return {
        "run_root": str(paths["run_root"]),
        "final_dir": str(paths["final_dir"]),
        "metrics": metrics,
    }


def parse_args() -> TrainConfig:
    parser = argparse.ArgumentParser(
        description="Train a QLoRA adapter for extinction-risk report drafting.")
    parser.add_argument("--train_jsonl", required=True,
                        help="Path to synthetic dataset JSONL")
    parser.add_argument("--model_name", default=os.environ.get("MODEL_NAME",
                        "Qwen/Qwen2.5-7B-Instruct"), help="Base model")
    parser.add_argument(
        "--output_dir", default="/content/drive/MyDrive/ecopath/extinction_risk", help="Base output directory")
    parser.add_argument(
        "--drive_root", default="/content/drive/MyDrive", help="Google Drive mount root")
    parser.add_argument("--run_name", default="exp_001",
                        help="Name for this training run")
    parser.add_argument("--max_seq_length", type=int, default=4096)
    parser.add_argument("--per_device_train_batch_size", type=int, default=1)
    parser.add_argument("--gradient_accumulation_steps", type=int, default=8)
    parser.add_argument("--learning_rate", type=float, default=2e-4)
    parser.add_argument("--num_train_epochs", type=float, default=3.0)
    parser.add_argument("--warmup_ratio", type=float, default=0.03)
    parser.add_argument("--logging_steps", type=int, default=10)
    parser.add_argument("--save_steps", type=int, default=100)
    parser.add_argument("--eval_steps", type=int, default=100)
    parser.add_argument(
        "--eval_split_ratio", type=float, default=0.15,
        help="Fraction held out for final evaluation (default: 0.15 = 15/100 Gemini records)",
    )
    parser.add_argument("--split_output_dir", default=None,
                        help="Optional directory for train/eval split JSONL files")
    parser.add_argument("--resume_from_checkpoint", default=None,
                        help="Optional checkpoint path to resume training from")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--lora_r", type=int, default=16)
    parser.add_argument("--lora_alpha", type=int, default=32)
    parser.add_argument("--lora_dropout", type=float, default=0.05)
    parser.add_argument(
        "--target_modules", default="q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj")
    parser.add_argument("--bf16", action="store_true",
                        help="Prefer bf16 if CUDA supports it")
    parser.add_argument("--no_gradient_checkpointing",
                        action="store_true", help="Disable gradient checkpointing")
    parser.add_argument("--push_to_hub", action="store_true")
    parser.add_argument(
        "--hub_model_id", default=os.environ.get("HUB_MODEL_ID"))
    parser.add_argument("--hub_token", default=os.environ.get("HUB_TOKEN"))

    args = parser.parse_args()
    return TrainConfig(
        train_jsonl=args.train_jsonl,
        model_name=args.model_name,
        output_dir=args.output_dir,
        drive_root=args.drive_root,
        run_name=args.run_name,
        max_seq_length=args.max_seq_length,
        per_device_train_batch_size=args.per_device_train_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        num_train_epochs=args.num_train_epochs,
        warmup_ratio=args.warmup_ratio,
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        eval_steps=args.eval_steps,
        eval_split_ratio=args.eval_split_ratio,
        split_output_dir=args.split_output_dir,
        resume_from_checkpoint=args.resume_from_checkpoint,
        seed=args.seed,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=args.target_modules,
        bf16=args.bf16,
        gradient_checkpointing=not args.no_gradient_checkpointing,
        push_to_hub=args.push_to_hub,
        hub_model_id=args.hub_model_id,
        hub_token=args.hub_token,
    )


if __name__ == "__main__":
    config = parse_args()
    result = train(config)
    print(json.dumps(result, indent=2))
