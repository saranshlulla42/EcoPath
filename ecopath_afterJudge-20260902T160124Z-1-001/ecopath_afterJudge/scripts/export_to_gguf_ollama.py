"""
Export a trained QLoRA adapter into a local Ollama-friendly GGUF model.

This script intentionally keeps the steps explicit because the exact conversion
commands vary slightly across model families and host machines.

Recommended workflow:
1. Merge the adapter into the base model.
2. Save the merged HF model to disk.
3. Convert the merged model to GGUF using llama.cpp tooling.
4. Create an Ollama Modelfile that points at the GGUF file.
5. Run `ollama create --quantize q4_K_M` to register a fast local model.

The script writes the artifacts and the Modelfile, then prints the follow-up
commands you should run in a terminal.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def merge_adapter(base_model: str, adapter_dir: Path, output_dir: Path, device_map: str | None = None) -> None:
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        device_map=device_map,
        torch_dtype=torch.float16,
        low_cpu_mem_usage=False,
        trust_remote_code=True,
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model, use_fast=True)

    # Lazy import so the script can still be inspected without peft installed.
    from peft import PeftModel

    peft_model = PeftModel.from_pretrained(model, str(adapter_dir))
    merged = peft_model.merge_and_unload()

    ensure_dir(output_dir)
    merged.save_pretrained(str(output_dir), safe_serialization=True)
    tokenizer.save_pretrained(str(output_dir))


def write_modelfile(modelfile_path: Path, gguf_path: Path, ollama_name: str) -> None:
    content = (
        f"FROM {gguf_path.as_posix()}\n\n"
        "PARAMETER temperature 0.2\n"
        "PARAMETER top_p 0.9\n"
        "PARAMETER num_predict 700\n\n"
        "PARAMETER stop \"<|im_end|>\"\n"
        "PARAMETER stop \"<|im_start|>\"\n\n"
        "SYSTEM You are a conservation science assistant drafting concise decision-support reports for human experts. Use only the provided species profile and evidence. Return JSON only.\n\n"
        'TEMPLATE """{{ if .System }}<|im_start|>system\\n{{ .System }}<|im_end|>\\n{{ end }}{{ if .Prompt }}<|im_start|>user\\n{{ .Prompt }}<|im_end|>\\n{{ end }}<|im_start|>assistant\\n"""\n'
    )
    modelfile_path.write_text(content, encoding="utf-8")


def write_next_steps(path: Path, merged_dir: Path, gguf_path: Path, ollama_name: str) -> None:
    instructions = {
        "merged_model_dir": str(merged_dir),
        "gguf_path": str(gguf_path),
        "ollama_model_name": ollama_name,
        "commands": [
            "# Convert the merged HF model to GGUF using llama.cpp (run from the llama.cpp repo)",
            f"python convert_hf_to_gguf.py \"{merged_dir}\" --outfile \"{gguf_path}\"",
            "",
            "# Register the quantized model in Ollama",
            f"ollama create --quantize q4_K_M {ollama_name} -f \"{path / 'Modelfile'}\"",
            "",
            "# Verify it loads",
            f"ollama run {ollama_name}",
        ],
    }
    (path / "export_instructions.json").write_text(json.dumps(instructions,
                                                              indent=2), encoding="utf-8")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export a merged adapter for Ollama/GGUF usage.")
    parser.add_argument("--base-model", required=True,
                        help="Base instruct model name or local path")
    parser.add_argument("--adapter-dir", required=True,
                        help="Directory containing the trained LoRA adapter")
    parser.add_argument("--output-dir", required=True,
                        help="Directory for merged/exported artifacts")
    parser.add_argument("--gguf-path", required=True,
                        help="Target GGUF output path")
    parser.add_argument("--device-map", default=None,
                        help="Optional device_map for loading the base model; default loads on CPU for safer merging")
    parser.add_argument("--ollama-name", default=os.environ.get("OLLAMA_REPORT_MODEL",
                        "ecopath-extinction-risk"), help="Local Ollama model name")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    adapter_dir = Path(args.adapter_dir)
    output_dir = ensure_dir(Path(args.output_dir))
    gguf_path = Path(args.gguf_path)

    merge_adapter(args.base_model, adapter_dir,
                  output_dir, device_map=args.device_map)
    write_modelfile(output_dir / "Modelfile", gguf_path, args.ollama_name)
    write_next_steps(output_dir, output_dir, gguf_path, args.ollama_name)

    print(json.dumps({
        "merged_model_dir": str(output_dir),
        "gguf_path": str(gguf_path),
        "ollama_model_name": args.ollama_name,
    }, indent=2))


if __name__ == "__main__":
    main()
