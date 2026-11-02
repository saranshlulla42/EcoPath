# Paper revision map

Verified replacement text is in `VERIFIED_PAPER_SECTIONS.md`; the existing `research_paper_technical_methodology.txt` now points to and reflects this audited scope. The broader `EcoPath_Report_Corrected.md` carries a revision notice because its platform claims predate this experiment. No editable source for a separate QLoRA results manuscript was found; apply this map to that manuscript manually if it exists elsewhere.

| Section | Required revision and evidence |
|---|---|
| Title | Prefer “Evaluating evidence-constrained conservation report drafting in EcoPath” until a completed comparison supports a stronger claim. Avoid “accurate extinction prediction”, “validated conservation assessment” and automatic QLoRA superiority. |
| Abstract | State implemented platform, 100 taxonomy-only examples, 85/15 split, saved JSON counts, weak-prompt limitation and pending stronger-baseline study. Separate software tests from ecological experiments. |
| Research question/hypothesis | Ask whether adaptation improves supplied-evidence fidelity and abstention relative to strong prompt/schema/template controls, accounting for structural failures and cost. Allow null/mixed results. |
| Architecture | Separate the live hybrid retrieval/heuristic/repair/report path from the offline fixed-evidence HF comparison. Do not assign fallback content or platform sources to the model experiment. Distinguish implemented, code-only, tested with mocks, and live-verified features. |
| Dataset and provenance | Report 100 unique names, 31 families, 16 orders, GBIF taxonomy snippets only, all ecological fields missing, no verified India frame. List source URLs, missing retrieval dates and absent builder/teacher records. Provide inventory/hash manifests. |
| Splits | Report original 85/15 species split and Larus/Turdus genus overlap; no validation-based checkpoint selection evidence. Describe the new genus-grouped, pilot-excluded train/validation/test protocol only as implemented/planned until real data exists. |
| Training | State record-supported LoRA/TrainingArguments values, manual-role-token mismatch, no immutable base revision or measured training cost. Distinguish code defaults from observed state. New assistant-masked three-seed training remains pending. |
| Inference | Include exact original prompt and script reference, native evaluation template, weak schema instruction, default versus unknown effective CLI, adapter loading and quantisation choices. New primary controls share evidence/prompt/constraints where appropriate. |
| Evaluation | Rename original “schema compliance” to “required-key presence”. Report strict/relaxed parsing separately. Add field support, abstention, citation and structural metrics with denominators, zero cases, failure treatment, species aggregation and annotations. No prose entailment from string similarity. |
| LLM judge | Report original truncated context, supplementary scores and unrecorded effective model/settings/retries. Flag possible teacher–judge overlap. Remove “independent”, “validated”, “expert assessed”, or “human evaluation” descriptions unless substantiated. |
| Results | Preserve 0/15 versus 15/15 as original saved-output formatting result. Mark new model, per-evidence-level, three-seed, human and cost result cells PENDING. Fixture and taxonomy-template diagnostics must be separately labelled. |
| Discussion | Explain that all-missing ecological data cannot assess available-evidence use or false abstention. JSON compliance is useful engineering behavior but insufficient evidence of conservation fidelity. Stronger baselines may remove the need for adaptation. |
| Limitations | Missing builder/teacher/hardware/revision records, only 15 evaluated species, global/unverified sampling, genus overlap, weak prompt, all-missing ecology, heterogeneous teacher targets, heuristic unsupported language, incomplete judge context, no human validation, and pending trained comparisons. |
| Conclusion | State the observed formatting difference and the implemented evaluation framework. Do not claim conservation benefit, superiority, generalisation, statistical significance or cost savings before results exist. |
| Reproducibility appendix | Include immutable manifest, dataset contract, exact commands/configurations, prompts/chat-template hash, runtime versions, raw outputs/errors/attempts, planned IDs and blinding/adjudication workflow. Mark unavailable records explicitly. |
| AI-use declaration | Disclose teacher-generated targets with exact identity unavailable; supplementary Gemini judging; coding/analysis assistance for this revision; and required human verification. Investigators must approve the final declaration. |
| Data access | Describe GBIF source URLs and applicable publisher licences, missing original access records, IUCN permission/token requirements, and no redistribution of restricted records. New pilot requires a documented source/licence ledger. |
| Novelty and related work | All “first”, “no prior work”, and broad superiority claims need a scoped systematic literature review across grounding, abstention, structured generation and conservation decision support. This audit is not that literature review. |

Recommended original-results wording:

> Re-analysis of the saved outputs found valid JSON in 0 of 15 base-model responses and 15 of 15 adapted-model responses. The prompt did not explicitly request a JSON schema, and the saved evidence contained taxonomy but no ecological status, trend, population, habitat or range values. This comparison demonstrates a formatting difference under the original condition; it does not establish improved evidence fidelity or superiority to engineered or constrained baselines.

Pending-results table shell:

| Phase | Method | Species | Evidence variants | JSON/schema | Field use/abstention | Human prose support | Training/inference cost |
|---|---|---:|---|---|---|---|---|
| Original | base | 15 | one taxonomy-only input/species | 0/15 JSON; 0/15 keys | not established | not assessed | unavailable |
| Original | adapted, one saved seed | 15 | same evidence | 15/15 JSON; 15/15 keys | not established | not assessed | unavailable |
| Pilot | original/engineered/constrained/template | pending ~30 | complete/partial/minimal | pending | pending | pending | pending |
| Final | frozen methods and adapted seeds if justified | pending | grouped by species | pending | pending | pending | pending |

A status classifier's F1 is inappropriate for the current experiment: no supplied IUCN label exists. Any future category reporting must be source quotation, not inference of official conservation categories from sparse input. Uncorrected occurrence density must not be labelled population abundance or population decline. “Causal reasoning” is a platform description, not validated causal identification.
