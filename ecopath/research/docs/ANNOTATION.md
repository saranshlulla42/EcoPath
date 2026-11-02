# Human annotation and adjudication guide

Purpose: assess factual support in free text and suggested actions. Deterministic structured checks establish agreement with supplied extraction assertions only. Neither ecological plausibility nor matching a reference report proves source support.

Export randomized packets with `research.cli annotate`. Give reviewers `blind_review.jsonl` without `PRIVATE_blinding_key.jsonl`, method/seed identifiers, reference targets or other model outputs. Text style may make complete blinding impossible; record suspected unblinding. Use the evidence payload as the allowed evidence. Provenance links identify the collected records; do not add remembered or newly retrieved facts. Hidden complete-record references are not part of the label task. For masked examples, original provenance text can contain extra facts: use only the displayed canonical assertions for primary supplied-evidence labels, with a separate later extraction-quality audit if needed.

Two reviewers independently segment factual statements into atomic claims. Include factual clauses in suggested actions: “Consider monitoring” is a proposal; “because the population is declining” is a factual claim requiring evidence. Review identity claims, IUCN categories, numbers, locations, trends, threat assertions, and causal language. A source existing or mentioning the species does not show it supports each claim.

| Label | Meaning | Non-ecological example |
|---|---|---|
| supported | supplied assertion entails the claim for this identity/field | evidence says fixture token A; claim repeats token A |
| contradicted | supplied evidence explicitly disagrees | evidence token A; claim says supplied value is token B |
| unsupported | factual claim exceeds the supplied evidence | source is taxonomy only; claim introduces a fixture count |
| unverifiable | ambiguity prevents a reliable judgement | assertion scope/time/identity cannot be resolved |
| not_factual | proposal or explicit uncertainty without embedded factual assertion | “Consider collecting the missing fixture field” |
| unassessable | no usable output/claim can be assessed | empty, truncated or structurally invalid response |

For every segment record `claim_text`, `label`, `source_ids`, and `rationale`, plus optional evidence excerpt and scope/time caveat. Citation labels should additionally distinguish missing citation, unknown ID, existing-but-nonsupporting citation, and supporting citation. Do not reward “unavailable” on an available field; record false abstention. If an official category is absent, a correct real-world category still counts unsupported in this experiment. No-claim reports are not perfect evidence use: judge whether available fields were omitted and keep assessability/field coverage alongside claim precision.

Complete packet `reviewer_id`, `label_origin:"human"`, `labels`, and `overall_evidence_use` (`supported_and_complete`, `unsupported_or_incomplete`, or `unassessable`). Factual claim records may encode `citation_label` as `missing`, `unknown`, `exists_not_supporting`, or `supporting`; omitted labels remain explicitly not recorded. Keep `llm_assisted` and `automated` labels in separate records, never rebrand them human. Preserve annotation guide version, reviewer training material, date and any conflicts of interest. Train reviewers using synthetic/development examples; do not resolve disagreements by revealing method identity.

`adjudicate` joins reviews by opaque annotation ID, rejects duplicate reviewers/invalid labels, separates supplementary labels and produces a pending-adjudication file. It does not automatically resolve disagreement. A named adjudicator reviews both rationales, records claim alignment, final labels, evidence IDs, justification and guide changes. A single review remains pending. Equal label lists are marked agreement, not validated truth. The implementation compares full label records conservatively; harmless rationale differences can also flag adjudication. Record these cases.

Before a final study, freeze claim segmentation rules, how citation labels are encoded, adjudication export format, annotator eligibility and the planned agreement statistic. Claim segmentation and human agreement calculations require human-aligned claim units; the software does not invent those alignments. Report reviewer counts, agreements/disagreements, unresolved cases, abstentions, and both pre-adjudication and adjudicated outcomes. Keep source-extraction validation distinct from output support annotation.

LLM judges are supplementary only. If later enabled, save judge provider/exact model revision, rubric version, full evidence/prompt, settings, raw response, individual labels, errors/retries and teacher overlap. No paid judging is launched by this pipeline. The original judge's incomplete context and unvalidated rubric preclude an independence or validation claim.

Use `annotation-summary` after agreement or named adjudication. It keeps pending records out of completed label totals, reports review coverage and null no-claim precision, counts structurally unassessable reports as failures, and excludes supplementary labels. Adjudicators supply `adjudicated_overall_evidence_use` with their final labels.
