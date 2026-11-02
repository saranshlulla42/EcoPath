r"""
grade_results.py  –  Step 3: Automated judge for EcoPath model comparison.

This script reads eval_results.jsonl (produced by run_evaluation.py) and scores
each row on four dimensions:

  1. JSON Validity          – did the model return parseable JSON?
  2. Schema Compliance      – does it contain all required keys?
  3. IUCN Status Accuracy   – does the extracted status match ground truth (when available)?
  4. Gemini LLM Judge Score – uses Gemini to rate each output 1-5 for
                               factuality, completeness, and format.

The final report (eval_report.json + eval_summary.md) shows a side-by-side
table suitable for pasting directly into the research paper.

Usage:
  python scripts/grade_results.py \
      --results  dataset/eval_results.jsonl \
      --output   dataset/eval_report.json \
      --summary  dataset/eval_summary.md \
      --gemini-api-key  YOUR_KEY   \   # or set GEMINI_API_KEY env var
      --skip-llm-judge               # omit to run the LLM judge

Requirements:
  pip install httpx google-generativeai
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)

# ---------------------------------------------------------------------------
# Required JSON keys that a well-formed EcoPath report must contain
# ---------------------------------------------------------------------------
REQUIRED_KEYS = {
    "decision_support_draft": {
        "species",
        "current_conservation_status",
        "key_threats",
        "survivability_assessment",
        "mitigation_actions",
        "sources",
    }
}


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def is_valid_json(text: str) -> tuple[bool, Any]:
    """Return (is_valid, parsed_object). Strips markdown fences if present."""
    if text is None:
        return False, None
    # Strip ```json ... ``` fences
    cleaned = re.sub(r"```(?:json)?\s*([\s\S]*?)```", r"\1", text.strip())
    # Also strip bare ``` fences
    cleaned = re.sub(r"^```\w*\s*", "", cleaned.strip())
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())
    try:
        return True, json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find the first { ... } block
        m = re.search(r"(\{[\s\S]*\})", cleaned)
        if m:
            try:
                return True, json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    return False, None


def check_schema(parsed: Any) -> tuple[bool, list[str]]:
    """
    Returns (passes, missing_keys).
    Accepts two layouts:
      1. Nested: required keys inside parsed["decision_support_draft"] (a dict)
      2. Flat:   required keys at the top level of parsed (FT model output style)
    """
    if not isinstance(parsed, dict):
        return False, list(REQUIRED_KEYS["decision_support_draft"])

    draft = parsed.get("decision_support_draft")

    # Layout 1: nested dict under decision_support_draft
    if isinstance(draft, dict):
        missing = [k for k in REQUIRED_KEYS["decision_support_draft"] if k not in draft]
        return len(missing) == 0, missing

    # Layout 2: fields at top level (flat structure)
    missing = [k for k in REQUIRED_KEYS["decision_support_draft"] if k not in parsed]
    return len(missing) == 0, missing


def extract_iucn_status(parsed: Any) -> Optional[str]:
    """Pull current_conservation_status out of a parsed EcoPath JSON.
    Handles both nested (under decision_support_draft) and flat layouts.
    """
    if not isinstance(parsed, dict):
        return None
    draft = parsed.get("decision_support_draft")
    # Layout 1: nested dict
    if isinstance(draft, dict):
        return draft.get("current_conservation_status")
    # Layout 2: flat — field at top level
    return parsed.get("current_conservation_status")


def iucn_match(predicted: Optional[str], ground_truth: Optional[str]) -> Optional[bool]:
    """Return None if ground truth is missing, else True/False."""
    if not ground_truth:
        return None
    if not predicted:
        return False
    # Normalise: lowercase, strip whitespace & punctuation
    def norm(s: str) -> str:
        return re.sub(r"[^a-z]", "", s.lower())
    return norm(predicted) == norm(ground_truth)


# ---------------------------------------------------------------------------
# Gemini LLM judge
# ---------------------------------------------------------------------------
JUDGE_PROMPT_TEMPLATE = """\
You are an expert conservation biologist and AI evaluator.

You will be shown a model's output for an extinction-risk decision-support report.
Score it on the following criteria, using integer scores from 1 to 5:

1. **Format Compliance** (1-5): Is the output valid, well-structured JSON matching the expected schema?
   - 5 = Perfect JSON, all required keys present
   - 1 = Not JSON at all or completely broken structure

2. **Factual Accuracy** (1-5): Are the conservation status, threats, and mitigation actions ecologically plausible and grounded in the provided evidence?
   - 5 = Highly accurate, evidence-grounded
   - 1 = Hallucinates, contradicts evidence, or makes up facts

3. **Completeness** (1-5): Does the report cover all required sections (status, threats, survivability, mitigation, sources)?
   - 5 = All sections present and substantive
   - 1 = Mostly empty or missing key sections

4. **Usefulness** (1-5): Would a conservation expert find this report actionable and informative?
   - 5 = Highly actionable, expert-ready
   - 1 = Useless or misleading

Return ONLY a JSON object in this exact format:
{{
  "format_compliance": <int>,
  "factual_accuracy": <int>,
  "completeness": <int>,
  "usefulness": <int>,
  "brief_reason": "<one sentence>"
}}

---

### Species
{species}

### Evidence provided to the model
{evidence_snippet}

### Model Output to Score
{model_output}
"""


def call_gemini_judge(
    api_key: str,
    species: str,
    evidence_snippet: str,
    model_output: str,
    model_name: str = "gemini-3.6-flash",
    retries: int = 4,
    delay: float = 3.0,
) -> dict[str, Any]:
    """
    Call the Gemini API to score a single model output.
    Requests JSON mode via generationConfig and uses exponential backoff.
    Falls back to a zero-score dict on error.
    """
    # Clean API key to prevent URL parsing errors
    clean_key = api_key.strip("'\" \t\r\n")

    prompt = JUDGE_PROMPT_TEMPLATE.format(
        species=species,
        evidence_snippet=evidence_snippet[:800],
        # Do not cut a JSON response mid-object: doing so makes the external
        # judge incorrectly score a valid model output as truncated/invalid.
        # The evaluation outputs are small enough to include in full.
        model_output=model_output if model_output else "(no output)",
    )

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_name}:generateContent"
    )
    headers = {"x-goog-api-key": clean_key}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 1024,
            "responseMimeType": "application/json",
        },
    }

    current_delay = delay
    for attempt in range(retries + 1):
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                body = resp.json()
                parts = body["candidates"][0]["content"]["parts"]
                raw_text = next(
                    (part["text"] for part in parts if "text" in part), ""
                )
                valid, parsed = is_valid_json(raw_text)
                if valid and isinstance(parsed, dict):
                    required = {
                        "format_compliance", "factual_accuracy",
                        "completeness", "usefulness", "brief_reason",
                    }
                    scores_valid = all(
                        isinstance(parsed.get(key), int) and 1 <= parsed[key] <= 5
                        for key in required - {"brief_reason"}
                    )
                    if required.issubset(parsed) and scores_valid:
                        return parsed
                    log.warning("Gemini returned an invalid judge schema for %s (attempt %d)", species, attempt + 1)
                    continue
                log.warning("Gemini returned non-JSON for %s (attempt %d)", species, attempt + 1)
        except Exception as exc:  # noqa: BLE001
            detail = resp.text[:500] if "resp" in locals() else str(exc)
            log.warning("Gemini call failed for %s: %s (attempt %d)", species, detail, attempt + 1)

            # Gemini returns a human-readable retry interval with 429 errors.
            # Respect it instead of immediately consuming every retry.
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                retry_match = re.search(r"retry in\s+([0-9.]+)s", detail, re.IGNORECASE)
                if retry_match:
                    current_delay = max(current_delay, float(retry_match.group(1)) + 2.0)

        if attempt < retries:
            time.sleep(current_delay)
            current_delay *= 1.5  # Exponential backoff for 503s and rate limits

    return {
        "format_compliance": 0,
        "factual_accuracy": 0,
        "completeness": 0,
        "usefulness": 0,
        "brief_reason": "Gemini judge call failed",
    }


# ---------------------------------------------------------------------------
# Per-row scoring
# ---------------------------------------------------------------------------
@dataclass
class RowScores:
    idx: int
    species: str
    scientific_name: str
    iucn_ground_truth: Optional[str]

    base_json_valid: bool = False
    base_schema_ok: bool = False
    base_missing_keys: list[str] = field(default_factory=list)
    base_iucn_extracted: Optional[str] = None
    base_iucn_match: Optional[bool] = None
    base_judge: dict[str, Any] = field(default_factory=dict)

    ft_json_valid: bool = False
    ft_schema_ok: bool = False
    ft_missing_keys: list[str] = field(default_factory=list)
    ft_iucn_extracted: Optional[str] = None
    ft_iucn_match: Optional[bool] = None
    ft_judge: dict[str, Any] = field(default_factory=dict)

    has_ft: bool = False


def score_row(
    record: dict[str, Any],
    api_key: Optional[str],
    skip_llm: bool,
    judge_model: str,
) -> RowScores:
    idx = record["idx"]
    species = record.get("species", "")
    sci = record.get("scientific_name", "")
    gt_iucn = record.get("iucn_status_ground_truth")
    base_raw = record.get("base_model_output", "")
    ft_raw = record.get("ft_model_output")
    has_ft = ft_raw is not None

    # Evidence snippet for judge context
    evidence_snippet = record.get("prompt_user", "")[:600]

    rs = RowScores(
        idx=idx,
        species=species,
        scientific_name=sci,
        iucn_ground_truth=gt_iucn,
        has_ft=has_ft,
    )

    # ---- Base model ----
    rs.base_json_valid, base_parsed = is_valid_json(base_raw)
    if rs.base_json_valid:
        rs.base_schema_ok, rs.base_missing_keys = check_schema(base_parsed)
        rs.base_iucn_extracted = extract_iucn_status(base_parsed)
        rs.base_iucn_match = iucn_match(rs.base_iucn_extracted, gt_iucn)
    if not skip_llm and api_key:
        rs.base_judge = call_gemini_judge(
            api_key, species, evidence_snippet, base_raw or "", judge_model
        )

    # ---- Fine-tuned model ----
    if has_ft:
        rs.ft_json_valid, ft_parsed = is_valid_json(ft_raw)
        if rs.ft_json_valid:
            rs.ft_schema_ok, rs.ft_missing_keys = check_schema(ft_parsed)
            rs.ft_iucn_extracted = extract_iucn_status(ft_parsed)
            rs.ft_iucn_match = iucn_match(rs.ft_iucn_extracted, gt_iucn)
        if not skip_llm and api_key:
            rs.ft_judge = call_gemini_judge(
                api_key, species, evidence_snippet, ft_raw or "", judge_model
            )

    return rs


# ---------------------------------------------------------------------------
# Aggregate statistics
# ---------------------------------------------------------------------------

def aggregate(rows: list[RowScores]) -> dict[str, Any]:
    n = len(rows)
    ft_rows = [r for r in rows if r.has_ft]
    n_ft = len(ft_rows)

    def pct(lst: list[bool]) -> float:
        return round(100.0 * sum(lst) / len(lst), 1) if lst else 0.0

    def avg_judge(rows_in: list[RowScores], key: str, attr: str) -> float:
        vals = [r.__dict__[attr].get(key, 0) for r in rows_in if r.__dict__[attr]]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    base_stats: dict[str, Any] = {
        "n_samples": n,
        "json_valid_pct": pct([r.base_json_valid for r in rows]),
        "schema_ok_pct": pct([r.base_schema_ok for r in rows]),
    }
    iucn_rows_base = [r for r in rows if r.base_iucn_match is not None]
    if iucn_rows_base:
        base_stats["iucn_accuracy_pct"] = pct([r.base_iucn_match for r in iucn_rows_base])
        base_stats["iucn_n_evaluated"] = len(iucn_rows_base)

    ft_stats: dict[str, Any] = {"n_samples": n_ft}
    if ft_rows:
        ft_stats["json_valid_pct"] = pct([r.ft_json_valid for r in ft_rows])
        ft_stats["schema_ok_pct"] = pct([r.ft_schema_ok for r in ft_rows])
        iucn_rows_ft = [r for r in ft_rows if r.ft_iucn_match is not None]
        if iucn_rows_ft:
            ft_stats["iucn_accuracy_pct"] = pct([r.ft_iucn_match for r in iucn_rows_ft])
            ft_stats["iucn_n_evaluated"] = len(iucn_rows_ft)

    # LLM judge averages
    judge_keys = ["format_compliance", "factual_accuracy", "completeness", "usefulness"]
    for k in judge_keys:
        if any(r.base_judge for r in rows):
            base_stats[f"judge_{k}_avg"] = avg_judge(rows, k, "base_judge")
        if any(r.ft_judge for r in ft_rows):
            ft_stats[f"judge_{k}_avg"] = avg_judge(ft_rows, k, "ft_judge")

    return {"base_model": base_stats, "ft_model": ft_stats}


# ---------------------------------------------------------------------------
# Markdown summary
# ---------------------------------------------------------------------------

def build_markdown(stats: dict[str, Any], rows: list[RowScores]) -> str:
    b = stats["base_model"]
    f = stats["ft_model"]
    has_ft = f.get("n_samples", 0) > 0

    lines: list[str] = [
        "# EcoPath Model Evaluation Report",
        "",
        "## Summary Statistics",
        "",
    ]

    # Quantitative table
    metrics = [
        ("JSON Validity (%)", "json_valid_pct"),
        ("Schema Compliance (%)", "schema_ok_pct"),
        ("IUCN Status Accuracy (%)", "iucn_accuracy_pct"),
        ("Judge: Format (avg/5)", "judge_format_compliance_avg"),
        ("Judge: Factual Accuracy (avg/5)", "judge_factual_accuracy_avg"),
        ("Judge: Completeness (avg/5)", "judge_completeness_avg"),
        ("Judge: Usefulness (avg/5)", "judge_usefulness_avg"),
    ]

    col_b = "Base Model (Qwen2.5-7B)"
    col_ft = "Fine-Tuned (EcoPath)"

    lines.append(f"| Metric | {col_b} | {col_ft} | Delta |")
    lines.append("|--------|---------|---------|-------|")

    for label, key in metrics:
        bv = b.get(key, "N/A")
        fv = f.get(key, "N/A") if has_ft else "N/A"
        if isinstance(bv, (int, float)) and isinstance(fv, (int, float)):
            delta = f"+{fv - bv:.1f}" if fv >= bv else f"{fv - bv:.1f}"
        else:
            delta = "—"
        lines.append(f"| {label} | {bv} | {fv} | {delta} |")

    lines += [
        "",
        f"> **n (base)** = {b['n_samples']} &emsp; **n (fine-tuned)** = {f['n_samples']}",
        "",
        "## Per-Species Results",
        "",
        "| # | Species | Base JSON? | FT JSON? | Base Schema? | FT Schema? | IUCN GT | Base Status | FT Status |",
        "|---|---------|-----------|---------|-------------|-----------|---------|------------|----------|",
    ]

    for r in rows:
        lines.append(
            f"| {r.idx} | {r.species} "
            f"| {'YES' if r.base_json_valid else 'NO'} "
            f"| {'YES' if r.ft_json_valid else ('NO' if r.has_ft else '—')} "
            f"| {'OK' if r.base_schema_ok else 'FAIL'} "
            f"| {'OK' if r.ft_schema_ok else ('FAIL' if r.has_ft else '—')} "
            f"| {r.iucn_ground_truth or '—'} "
            f"| {r.base_iucn_extracted or '—'} "
            f"| {r.ft_iucn_extracted or ('—' if r.has_ft else 'N/A')} |"
        )

    lines += [
        "",
        "## Interpretation",
        "",
        "- **JSON Validity**: fraction of outputs that could be parsed as JSON.",
        "- **Schema Compliance**: parsed JSON also contains all required keys.",
        "- **IUCN Accuracy**: extracted `current_conservation_status` matches the IUCN ground-truth label.",
        "- **Judge scores** are rated 1–5 by Gemini on format, factuality, completeness, and usefulness.",
        "",
        "> Generated by `grade_results.py`.",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Argument parsing & main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="EcoPath automated grader")
    p.add_argument(
        "--results",
        default="dataset/eval_results.jsonl",
        help="Path to eval_results.jsonl (output of run_evaluation.py)",
    )
    p.add_argument(
        "--output",
        default="dataset/eval_report.json",
        help="Where to write the full JSON report",
    )
    p.add_argument(
        "--summary",
        default="dataset/eval_summary.md",
        help="Where to write the markdown summary",
    )
    p.add_argument(
        "--gemini-api-key",
        default=os.environ.get("GEMINI_API_KEY", ""),
        help="Gemini API key for the LLM judge (or set GEMINI_API_KEY env var)",
    )
    p.add_argument(
        "--judge-model",
        default="gemini-3.6-flash",
        help="Gemini model to use as judge (default: gemini-3.6-flash)",
    )
    p.add_argument(
        "--skip-llm-judge",
        action="store_true",
        help="Skip the Gemini LLM judge (run only deterministic metrics)",
    )
    p.add_argument(
        "--llm-delay",
        type=float,
        default=3.0,
        help="Seconds between Gemini calls to avoid rate-limiting (default: 3.0)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    results_path = Path(args.results)
    if not results_path.exists():
        log.error("Results file not found: %s", results_path)
        log.error("Run run_evaluation.py first.")
        sys.exit(1)

    # Load records
    records: list[dict[str, Any]] = []
    for line in results_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))

    log.info("Loaded %d result records from %s", len(records), results_path)

    api_key = args.gemini_api_key.strip("'\" \t\r\n") if args.gemini_api_key else None
    if not args.skip_llm_judge and not api_key:
        log.warning(
            "No Gemini API key provided. LLM judge will be skipped. "
            "Pass --gemini-api-key or set GEMINI_API_KEY."
        )
        args.skip_llm_judge = True

    # Score all rows
    scored_rows: list[RowScores] = []
    for i, record in enumerate(records, start=1):
        species = record.get("species", f"#{i}")
        log.info("[%d/%d] Scoring: %s", i, len(records), species)
        rs = score_row(record, api_key, args.skip_llm_judge, args.judge_model)
        scored_rows.append(rs)
        if not args.skip_llm_judge and rs.has_ft:
            # Two Gemini calls per row; pause after each row to respect quota
            time.sleep(args.llm_delay)

    # Aggregate
    stats = aggregate(scored_rows)

    # Write JSON report
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "aggregate": stats,
        "rows": [asdict(r) for r in scored_rows],
    }
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("JSON report written to %s", output_path)

    # Write markdown summary
    md = build_markdown(stats, scored_rows)
    summary_path = Path(args.summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(md, encoding="utf-8")
    log.info("Markdown summary written to %s", summary_path)

    # Print headline numbers to console
    b = stats["base_model"]
    f = stats["ft_model"]
    print("\n" + "=" * 60)
    print("  ECOPATH EVALUATION RESULTS")
    print("=" * 60)
    print(f"  {'Metric':<35} {'Base':>8}  {'FT':>8}")
    print(f"  {'-'*35} {'----':>8}  {'--':>8}")
    print(f"  {'JSON Validity (%)':<35} {b.get('json_valid_pct', 'N/A'):>8}  {f.get('json_valid_pct', 'N/A'):>8}")
    print(f"  {'Schema Compliance (%)':<35} {b.get('schema_ok_pct', 'N/A'):>8}  {f.get('schema_ok_pct', 'N/A'):>8}")
    if "iucn_accuracy_pct" in b:
        print(f"  {'IUCN Accuracy (%)':<35} {b.get('iucn_accuracy_pct', 'N/A'):>8}  {f.get('iucn_accuracy_pct', 'N/A'):>8}")
    print("=" * 60)


if __name__ == "__main__":
    main()
