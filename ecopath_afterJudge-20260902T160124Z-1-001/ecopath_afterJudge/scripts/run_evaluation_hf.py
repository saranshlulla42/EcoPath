"""
run_evaluation_hf.py  --  Step 2 (HuggingFace / PEFT version)

Runs a side-by-side comparison of:
  • BASE MODEL  : Qwen/Qwen2.5-7B-Instruct  (vanilla, no fine-tuning)
  • FINE-TUNED  : same base + EcoPath QLoRA adapter (ecopath_run_3epochs/final/)

Both models receive IDENTICAL prompts built from the held-out eval.jsonl.
Outputs are written to eval_results.jsonl for grading by grade_results.py.

Usage:
  python scripts/run_evaluation_hf.py \\
      --eval-jsonl  /content/drive/MyDrive/ecopath/extinction_risk/ecopath_gemini100_run1/splits/eval.jsonl \\
      --adapter-dir ../ecopath/ecopath/extinction_risk/ecopath_run_3epochs/final \\
      --output      dataset/eval_results.jsonl \\
      --max-samples 15 \\
      --device      auto

Requirements:
  pip install torch transformers peft accelerate
  (CUDA strongly recommended -- 7B model needs ~16 GB VRAM for fp16)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Optional

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
from peft import PeftModel

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

BASE_MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"

# ---------------------------------------------------------------------------
# System prompt (same as training)
# ---------------------------------------------------------------------------
# System prompt — MUST match DEFAULT_SYSTEM_PROMPT in train_qlora_colab.py exactly.
SYSTEM_PROMPT = (
    "You are a conservation science assistant drafting a decision-support report "
    "for human experts. Use the provided species profile and evidence only. "
    "Do not invent statistics. State uncertainty clearly. Return a structured "
    "report with inline evidence and a reviewer-facing disclaimer."
)


def build_user_message(record: dict[str, Any]) -> str:
    """Reconstruct the user turn exactly as it was formatted during training.

    This MUST match the output of format_example() in train_qlora_colab.py.
    The fine-tuned model only recognises the prompt structure it was trained on;
    using a different format (e.g. ### Task / ### Species Profile) causes the
    model to produce garbage output while the base model scores normally.
    """
    input_block   = json.dumps(record["input"], ensure_ascii=True, indent=2)
    queries_block = json.dumps(record.get("search_queries", []), ensure_ascii=True, indent=2)
    results_block = json.dumps(record.get("search_results", []), ensure_ascii=True, indent=2)

    return (
        "Use the retrieved evidence to draft a decision-support report for human conservation experts.\n\n"
        f"SPECIES INPUT:\n{input_block}\n\n"
        f"SEARCH QUERIES:\n{queries_block}\n\n"
        f"SEARCH RESULTS:\n{results_block}\n\n"
        "Requirements:\n"
        "- Structure the response as a decision-support draft, not a verdict.\n"
        "- Include current conservation status, key threats, risk reasoning, mitigation actions, and sources.\n"
        "- Use IUCN-style reasoning when you discuss decline or range contraction.\n"
        "- Do not fabricate statistics.\n"
        "- Keep citations inline and human-verifiable.\n"
    )


# ---------------------------------------------------------------------------
# Model loader helpers
# ---------------------------------------------------------------------------

def load_tokenizer(model_id: str) -> Any:
    log.info("Loading tokenizer from %s ...", model_id)
    tok = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    return tok


def load_base_model(model_id: str, device: str, use_4bit: bool) -> Any:
    log.info("Loading BASE model %s (4bit=%s) ...", model_id, use_4bit)
    kwargs: dict[str, Any] = {
        "trust_remote_code": True,
        "torch_dtype": torch.float16,
    }
    if use_4bit:
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
        )
        kwargs["device_map"] = "auto"
    elif device == "auto":
        kwargs["device_map"] = "auto"
    else:
        kwargs["device_map"] = device

    model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
    model.eval()
    log.info("  Base model loaded.")
    return model


def load_ft_model(base_model: Any, adapter_dir: str) -> Any:
    log.info("Loading fine-tuned adapter from %s ...", adapter_dir)
    ft_model = PeftModel.from_pretrained(base_model, adapter_dir)
    ft_model.eval()
    log.info("  Fine-tuned model loaded.")
    return ft_model


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def generate(
    model: Any,
    tokenizer: Any,
    system: str,
    user: str,
    max_new_tokens: int = 1024,
    temperature: float = 0.1,
) -> str:
    """Apply chat template, run generation, return decoded output text."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user",   "content": user},
    ]
    try:
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = tokenizer(text, return_tensors="pt").to(model.device)

        with torch.no_grad():
            out_ids = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                do_sample=temperature > 0,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        # Slice off the input tokens
        generated = out_ids[0][inputs["input_ids"].shape[1]:]
        return tokenizer.decode(generated, skip_special_tokens=True)
    except Exception as exc:  # noqa: BLE001
        log.error("Generation error: %s", exc)
        return f"[ERROR] {exc}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="EcoPath HuggingFace evaluation runner (base vs. fine-tuned)"
    )
    p.add_argument(
        "--eval-jsonl",
        required=True,
        help="Path to the 15-record held-out eval.jsonl written by train_qlora_colab.py",
    )
    p.add_argument(
        "--adapter-dir",
        default="../ecopath/ecopath/extinction_risk/ecopath_run_3epochs/final",
        help="Path to the QLoRA adapter directory (contains adapter_config.json)",
    )
    p.add_argument(
        "--base-model",
        default=BASE_MODEL_ID,
        help=f"HuggingFace model ID for the base model (default: {BASE_MODEL_ID})",
    )
    p.add_argument(
        "--output",
        default="dataset/eval_results.jsonl",
        help="Output JSONL path (default: dataset/eval_results.jsonl)",
    )
    p.add_argument(
        "--max-samples",
        type=int,
        default=0,
        help="Maximum eval samples; 0 evaluates every held-out record (default: 0)",
    )
    p.add_argument(
        "--device",
        default="auto",
        help="Device: 'auto', 'cuda', 'cpu' (default: auto)",
    )
    p.add_argument(
        "--use-4bit",
        action="store_true",
        help="Load in 4-bit quantisation (requires bitsandbytes; saves VRAM)",
    )
    p.add_argument(
        "--max-new-tokens",
        type=int,
        default=1024,
        help="Max tokens to generate per sample (default: 1024)",
    )
    p.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="Sampling temperature (default: 0.1 -- near-greedy for JSON)",
    )
    p.add_argument(
        "--skip-base",
        action="store_true",
        help="Skip base model inference (useful if you already have base outputs)",
    )
    p.add_argument(
        "--skip-ft",
        action="store_true",
        help="Skip fine-tuned model inference",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    eval_path = Path(args.eval_jsonl)
    if not eval_path.exists():
        log.error("Eval file not found: %s", eval_path)
        sys.exit(1)

    adapter_path = Path(args.adapter_dir)
    if not adapter_path.exists() and not args.skip_ft:
        log.error("Adapter directory not found: %s", adapter_path)
        sys.exit(1)

    # Load eval records
    records: list[dict[str, Any]] = []
    for line in eval_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    if args.max_samples and args.max_samples < len(records):
        records = records[: args.max_samples]
    log.info("Loaded %d eval records from %s", len(records), eval_path)

    # ---------- Load tokenizer (shared between both models) ----------
    tokenizer = load_tokenizer(args.base_model)

    # ---------- Base model pass ----------
    base_outputs: list[Optional[str]] = [None] * len(records)
    if not args.skip_base:
        log.info("=" * 50)
        log.info("PASS 1 OF 2: BASE MODEL")
        log.info("=" * 50)
        base_model = load_base_model(args.base_model, args.device, args.use_4bit)

        for idx, record in enumerate(records, start=1):
            species_name = record.get("input", {}).get("species", {}).get("common_name", f"#{idx}")
            log.info("[%d/%d] Base model -> %s", idx, len(records), species_name)
            user_msg = build_user_message(record)
            base_outputs[idx - 1] = generate(
                base_model, tokenizer, SYSTEM_PROMPT, user_msg,
                max_new_tokens=args.max_new_tokens,
                temperature=args.temperature,
            )

        # Free VRAM before loading the FT model
        del base_model
        torch.cuda.empty_cache()
        log.info("Base model unloaded from VRAM.")

    # ---------- Fine-tuned model pass ----------
    ft_outputs: list[Optional[str]] = [None] * len(records)
    if not args.skip_ft:
        log.info("=" * 50)
        log.info("PASS 2 OF 2: FINE-TUNED MODEL")
        log.info("=" * 50)
        # Re-load base, then wrap with adapter
        ft_base = load_base_model(args.base_model, args.device, args.use_4bit)
        ft_model = load_ft_model(ft_base, str(adapter_path))

        for idx, record in enumerate(records, start=1):
            species_name = record.get("input", {}).get("species", {}).get("common_name", f"#{idx}")
            log.info("[%d/%d] Fine-tuned model -> %s", idx, len(records), species_name)
            user_msg = build_user_message(record)
            ft_outputs[idx - 1] = generate(
                ft_model, tokenizer, SYSTEM_PROMPT, user_msg,
                max_new_tokens=args.max_new_tokens,
                temperature=args.temperature,
            )

        del ft_model, ft_base
        torch.cuda.empty_cache()
        log.info("Fine-tuned model unloaded from VRAM.")

    # ---------- Write results ----------
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as out_fh:
        for idx, record in enumerate(records, start=1):
            species_info = record.get("input", {}).get("species", {})
            row = {
                "idx": idx,
                "species": species_info.get("common_name", ""),
                "scientific_name": species_info.get("scientific_name", ""),
                "iucn_status_ground_truth": species_info.get("iucn_status"),
                "prompt_user": build_user_message(record),
                "reference_output": record.get("output", ""),
                "base_model_output": base_outputs[idx - 1],
                "ft_model_output": ft_outputs[idx - 1],
                "base_model_tag": args.base_model if not args.skip_base else None,
                "ft_model_tag": str(adapter_path) if not args.skip_ft else None,
            }
            out_fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    log.info("Done! Results written to %s", output_path)
    log.info("Next step: python scripts/grade_results.py --results %s", output_path)


if __name__ == "__main__":
    main()
