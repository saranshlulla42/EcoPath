# Pilot and final experiment plan

Research question: does QLoRA improve fidelity to supplied evidence and appropriate abstention over engineered prompting, schema-constrained decoding and a deterministic evidence template, after accounting for structural reliability and cost? The working hypothesis is directional but unconfirmed. Null, mixed and negative findings must be retained.

## Dependency order and decision gate

1. Audit and preserve the original experiment. Recompute saved-output metrics without generating replacement outputs. Keep its weak prompt, taxonomy-only coverage, unknown effective settings and judge limitations explicit.
2. Curate a legitimate India sampling frame. Record its edition/date/URL, permission/licence, membership confirmation, inclusion/exclusion rationale, genus/family/order coverage, source retrieval dates and per-field missingness. Target approximately 30 pilot species across multiple genera and evidence-availability patterns. Availability coverage is a design variable, never a fabricated ecological value. Selection is genus round robin within eligible records; report its limitations rather than implying a representative probability sample of Indian birds.
3. Reserve all pilot species/genera as developmental. Obtain separate development species for validation examples and potential training, plus an untouched final pool. Publish hashes and ID manifests before constructing variants. If only a 30-species pilot frame is available, do not imply train/validation/test exists or reuse it as final test.
4. Compare original instructions, engineered instructions with schema and validation-set demonstrations, constrained engineered instructions, and the deterministic template on identical pilot payloads. Select prompts/examples/settings on validation data only. Human reviewers assess unrestricted claims and suggestions. Report baseline fidelity failures and false abstention with assessability, not just JSON counts.
5. Determine whether meaningful fidelity failures remain. A research decision about useful improvement must be documented by investigators; there is no unreviewed ecological or statistical threshold hard-coded here. If stronger baselines suffice, report that finding and do not automatically train. If adaptation is justified, train targets covering available and missing fields for seeds 42/43/44, selecting each checkpoint by validation loss. Retain all failures and per-seed outputs.
6. Freeze the final protocol, code, dataset, schema, demonstration IDs, model/tokenizer revision, adapter weights/provenance and intentional configuration differences. Set `phase=final`, `split=test`. Final evaluation must be a new frozen run, with no pilot genera, prompt tuning or checkpoint choice based on its outcomes. Record investigator sign-off and the planned primary metrics/comparisons in the study registry before opening results.

The provided fractions/seeds/budgets are proposed settings and may be changed using development coverage. They are not ecological decision rules, sample-size guarantees or evidence of adequate power. Final species sample size and annotation capacity need a documented precision/power rationale informed by pilot variability.

## Methods and controls

| Method | Prompt | Constraints | Adaptation |
|---|---|---|---|
| original | preserved weak system/requirements applied to the shared v2 evidence format | none | none |
| engineered | evidence-only instructions, null rules, explicit schema, frozen validation demonstrations | none | none |
| constrained | identical engineered messages | schema token filter | none |
| qlora | identical engineered messages and evidence | same schema token filter | one independently trained adapter per seed |
| template | direct copying from same supplied fields; null on missing | deterministic construction | none |

Optional `qlora_unconstrained` is secondary. Exact original-format reproduction uses the archived script and archived payloads as a separate condition. Never mix new v2 examples with the original result table. The new `original` condition changes evidence serialization, intentionally; it is not an exact rerun. Retrieval conditions require an implemented retrieval algorithm and separate protocol; the primary experiment is evidence-in-prompt with external retrieval disabled.

All learned methods use one pinned base/tokenizer commit, NF4/double-quantization setting and compute dtype. Adapter metadata must match it and include train/validation species/genera for leakage checks. Legacy adapters lack that provenance and remain secondary archival artifacts. Primary generation uses batch one, frozen common input/output token budgets and decoding settings, no evidence truncation, and no model-specific retries. Every difference (original instructions versus examples/schema; constraints; adapters; template runtime) is recorded. Prompt lengths naturally differ, so report actual token counts and costs.

The HF runner uses `apply_chat_template` with one tokenization step and explicit return type. The saved tokenizer and real LM Format Enforcer character/token interfaces were tested on CPU. A small bridge uses the library's public `TokenEnforcer` because its packaged Transformers integration imports a removed tokenizer-class location in the installed Transformers 5 environment. This verifies token-filter plumbing and tested schema cases, not successful GPU model generation. Full post-generation schema validation remains mandatory. A constrained decoder can still terminate at its length cap or fail; such outputs remain failures.

The original training script optimises all prompt+answer tokens in a manually serialized format. The new trainer applies the native template, masks prompt labels, rejects overlength samples rather than truncating evidence/targets, and selects epoch checkpoints by validation loss. It records the three seeds independently. The final test partition is rejected by the training input path.

## Persistence and cost

Freeze requires immutable revisions and exclusive artifact creation. The protocol includes code/data/schema/adapter hashes and planned examples. Runs verify it before executing, write a manifest, hold a process lock, and append/fsync each response. Successful or invalid completed generations are not regenerated on resume. Explicit `--retry-errors` appends a numbered attempt only for execution errors; attempts remain visible. A malformed/torn JSONL refuses to resume until the tail is preserved and repaired into a new audited run. No silent overwrite, repair or example deduplication occurs.

Persist raw/special-token responses, parsed objects, validation errors, prompts, payload hash, method/seed, token IDs/counts, finish reason, elapsed times, warmups and environment. Record single-example wall time excluding load/warmup, model loading, constraint setup and GPU peak memory scope. Template token counts are null, not zero model tokens. Training records wall time, single-GPU Trainer time/GPU hours, hardware and peak allocated memory including weight load; driver-level memory is not implied. Warmups, batching, software versions and hardware accompany comparisons. No training/inference cost is reconstructed for the original experiment.

Ollama application previews send actual schema objects through `format` and validate returned data. They may use GGUF exports with unknown upstream revision/quantisation, so their outputs are explicitly operational previews. They are not pooled into the primary HF results.

## Analysis and figures

Report every attempted example, structural validity, conditional assessable-content metrics, end-to-end field success, available use, correct/false abstention, unsupported structured claims, citation existence/validity/associated support, and human prose labels. Retain missing methods/seeds and failures. Do not describe string checks or an automated judge as validated semantic evaluation.

Primary paired uncertainty resamples species, retaining all evidence variants. Equal-species effects average within a species across variants, then average across species. The bootstrap additionally resamples entire training-seed runs across all selected species; shared adapter seeds across compared adaptation conditions are sampled jointly. Report per-seed results and whether training-seed variation is estimable. A single seed cannot estimate it. Complete grids are required for paired estimates; excluded species/missing cells are listed. Zero-denominator variant metrics remain null; primary use is the end-to-end field metric with fixed denominators. Avoid conditional-rate paired inferences with method-dependent assessability without a separately specified estimand.

Use the saved configuration for requested percentile confidence intervals, bootstrap seed and number of draws. No automatic significance claim is emitted. Small species N, selected sampling frame and sparse seed counts limit uncertainty/generalisation. Confidence intervals do not repair a confounded comparison. Original all-zero/all-one structural rates can yield degenerate bootstrap intervals; do not mistake them for population certainty.

Generate tables with `summarize`, paired estimates with `statistics`, and original audit figures with `backend/.venv/bin/python -m research.plots --audit-dir research/artifacts/original/audit --out research/artifacts/figures-v1`. Dataset composition/availability and all method/level/seed metrics are saved as JSON/CSV/Markdown. Cost/timing/configuration and error rows are traceable to run/example/attempt. When GPU/human results do not exist, leave those table cells pending instead of drawing substitute model-performance figures.
