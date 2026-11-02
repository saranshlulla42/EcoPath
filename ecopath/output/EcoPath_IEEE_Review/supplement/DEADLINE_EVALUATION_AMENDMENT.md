# Submission deadline evaluation amendment

Recorded 29 October 2026 before generating either prioritized held-out condition. The user explicitly authorized this reduced comparison and requested minimal paper edits preserving its purpose and typography.

## Scientific purpose

Evaluate whether a QLoRA-adapted Qwen2.5-7B-Instruct produces better evidence-bounded bird conservation report drafts than the unadapted model under matched prompting and schema constraints. Null or adverse results remain reportable.

## Prioritized comparison

- Existing frozen protocol: `research/artifacts/final-qwen-a09a354-v1/protocol.json`.
- Existing protocol hash: `b0fc3242e40019a55578a50c2d10f8663d4e5f0eab32a9bdc448270aea9e7d79`.
- Same reviewed-v4 dataset and all 60 held-out species, with complete, partial and minimal evidence variants: 180 examples per condition.
- Unadapted comparator: `constrained`.
- Adapted comparator: `qlora-42`, the first training seed in the original design. This choice is fixed before these two test arms are generated; it is not based on their test performance or the best validation loss across seeds.
- Shared engineered prompt, validation demonstration, native chat template, tokenizer/base revision, quantization, evidence, token budgets, schema constraints and decoding.
- Deterministic template already complete; retain as a construction reference.

The old seven-method protocol is not rewritten. Its preserved original-prompt partial results and previously completed pilot remain separate from the primary two-condition submission analysis. The original-prompt process is interrupted to prioritize the agreed comparison, retaining every completed row. The other planned methods/seeds are deferred due to the submission deadline, not dropped because of their test outcomes. Thus this is a disclosed reduction of the originally planned analysis, not a newly claimed preregistration or a completed seven-method experiment.

## Analysis fixed before prioritized outcomes

Primary outcome: equal-species end-to-end structured-field success, retaining structural failures, with all three variants kept within species. Use the existing species bootstrap implementation, 2,000 draws, seed 42, and report the paired effect and percentile interval. This resamples test species; one evaluated training seed cannot estimate variation across independent adapter training runs.

Secondary descriptive outcomes: JSON validity, full-schema compliance, supplied-value agreement, correct and false abstention, citation existence/validity/structured-source agreement, generation-cap hits, execution errors, token counts and measured inference time. Report denominators and evidence-variant breakdowns. Automated string/source checks do not establish semantic ecological correctness of unrestricted text.

No prompt, checkpoint, decoding or sample changes based on these two held-out conditions. No structural-failure replacement. Execution errors remain recorded; retries, if required, use the existing explicit retry mechanism. Do not pool the archived 15-species experiment with this 60-species comparison.

## Paper editing constraint

Preserve the supplied second draft's purpose, title, authors, typography, unaffected text, figures and page geometry wherever possible. Change only passages required to describe the new comparison accurately and correct the documented historical key-presence and truncated-judge-context problems. Prefer a PDF preserving the original page content, with a brief change log. Do not claim expert validation or add an expert approval requirement.

