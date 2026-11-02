# EcoPath paper: private review package

`main.tex` is the revised IEEE manuscript; `figures/` contains the two supplied figure PDFs. Your original files in Downloads were not changed. The manuscript preserves the stated research purpose and the supplied title and formatting while correcting claims and adding the necessary experimental details. The editable sources of the two diagrams were not supplied.

## Main finding and its limit

The matched comparison has 60 held-out species and three evidence variants each, giving 180 reports per condition and 1,620 field checks per condition. The original, prespecified punctuation-sensitive check yields 1,168/1,620 for the constrained base model and 1,620/1,620 for QLoRA: a paired difference of 27.9 percentage points, with a species-bootstrap 95% interval of 27.2–29.0 percentage points. Saved scores were independently recomputed from the stored outputs and matched the original scores.

Inspecting the output revealed that 435 of 443 assessable base-model value mismatches differ only by a terminal period. The remaining eight are shortened labels omitting the longer source-context phrase. These are not 443 demonstrated ecological errors. A post-hoc sensitivity check ignoring terminal periods yields 1,603/1,620 versus 1,620/1,620, a 1.05 percentage point paired difference (95% species-bootstrap interval 0.0–2.53 percentage points). The sensitivity analysis was chosen after inspection, and neither check establishes semantic or ecological correctness. Only one adapter seed was evaluated on this held-out test.

The earlier 15-species pilot used a different prompt and is historical context, not a matched estimate and not pooled with the main results.

## Reproducibility and contents

- `supplement/audit_summary.json`: data, prompt, configuration and score checks.
- `supplement/sensitivity_analysis.json`: post-hoc re-scoring and paired bootstrap.
- `supplement/baseline_mismatched_fields.json` and `supplement/illustrative_examples.json`: saved cases, including source IDs and original model outputs.
- `supplement/exact_messages_example.json`: complete messages for one actual test example, including the system instruction, schema, demonstration and test evidence. The evidence differs by test example; paired arms used identical input messages for each case. `exact_json_schema.json`, `exact_chat_template.jinja` and `exact_prompt_token_ids.json` preserve the other prompt components.
- `supplement/species_split_manifest.csv` and `variant_field_masks.csv`: assignments and masks for 120 species, including the 60 held-out test species.
- `supplement/all_variants.PRIVATE.jsonl`, `source_review_ledger.jsonl` and `taxonomy_crosswalk.jsonl`: source-linked material and the name crosswalk. The model-visible source excerpts are canonical wrappers built from extracted values, not verbatim source quotations. Source checking was AI-assisted; it was not independent expert validation.
- `supplement/matched_outputs.jsonl`, matched summaries, `frozen_protocol.json`, `frozen_code/`, adapter configuration/provenance and training result: preserved inputs, outputs and configuration. The trained adapter weights are not included.
- `supplement/build_evidence.py`: audit script as executed in the original project environment; paths and Python dependencies must be adjusted to run it elsewhere. Full model reproduction also requires the pinned backbone, adapter weights, compatible dependencies and GPU.

Inference used greedy decoding (temperature 0, one beam), a 4,096-token input budget and 768-token output budget. The constrained and QLoRA paths install LM Format Enforcer as a prefix-allowed-token function over the same report schema. An over-budget input raises an error rather than truncating evidence; generation exceptions are recorded as errors rather than silently switching to another model or an unconstrained fallback. One base output hit the output cap and was invalid JSON; its nine fields count as end-to-end failures. The raw matched outputs retain per-call timing and backend details.

The frozen protocol's stated SHA-256 `b0fc3242e40019a55578a50c2d10f8663d4e5f0eab32a9bdc448270aea9e7d79` hashes its canonical JSON body excluding `protocol_hash`. The byte-level SHA-256 of `frozen_protocol.json` is `6d40b43dec36ede49e37f989c5c49f8cd860f37af7082d187cacc9c48e6e7439`. These are different hashing procedures.

This is a private evidence package. It includes source-derived material; do not publicly redistribute it before checking the relevant rights, particularly for the later taxonomy cross-check. No public repository is claimed.

## Before submission

The target venue, author order, affiliations, email addresses, acknowledgments, funding and competing-interest statements are not finalized. Confirm them and apply the selected venue's submission and AI-use rules, page limits, accessibility and required template. The manuscript retains the supplied author information for now; it is not represented as final. Decide what material can be released and where. The original editable diagram sources were not supplied, although both diagram PDFs are included. No submission has been made.

See `REFERENCES_AUDIT.md` for source links and `MANIFEST.sha256` for file checksums if present.

## Compile

Compile `main.tex` with an IEEEtran-capable LaTeX installation from this directory, with both PDFs retained in `figures/`. For example, run `pdflatex main.tex` twice, or `tectonic main.tex` twice. The included review PDF was compiled with Tectonic; it is six A4 pages. The supplied figures are PDF 1.7 and Tectonic issued PDF-version warnings when embedding them in the PDF 1.5 output; both figures were visually inspected in the rendered output. Check the selected venue's PDF requirements before submission.
