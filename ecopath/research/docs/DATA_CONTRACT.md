# Dataset and evaluation contract v2

Version: `ecopath-evidence-v2`. Canonical implementation is `backend/evidence_contract.py`; `research.contract` reuses it. Output JSON Schema is exported under `schemas/report.schema.json`. The old UI response remains a separate backwards-compatible schema. No old targets or original results are rewritten into new results.

## Collected record

Each JSONL row has exactly `species_id`, `scientific_name`, `genus`, `taxonomy`, `sampling`, `dataset_version`, `fields`, and `sources`. IDs are stable catalogue identifiers such as `gbif:2495150`, not list indices. Taxonomy retains available family/order values and provenance in the original inventory; it is not used to infer ecology. The sampling block records country code, source URL of the sampling frame, membership review, selection rationale and exclusions where known. Unknown values remain null/unavailable.

Nine fields are evaluated: iucn_status, population_trend, population_size, habitat, range_summary, diet, breeding_behavior, migratory_behavior and key_threats. Each contains `{value, availability, source_ids}`. Availability is `available`, `missing`, or `conflicting`. Available requires a nonempty scalar/list and matching source assertions; missing/conflicting require null. Missing has no assertions; conflicting retains differing assertions privately and abstains visibly. Never collapse absent evidence into `NE` or `DD`. Those are official categories that may be copied only when explicitly supplied with a source.

Every source assertion has `source_id`, `record_id`, `url`, `retrieved_at`, `excerpt`, `field`, `value`, `license`, and `extraction_review`. Field/value support is a **curated extraction assertion**, not automatic proof that the source document entails that value. Real pilot/final runs require dated, licensed, reviewed extractions. Null retrieval timestamps are allowed only to honestly represent incomplete archival records; they block promotion to the pilot/final. Keep original excerpts, URLs, timestamps and source conflicts for human provenance review. Do not replace missing retrieval dates with today's audit date.

The importer rejects unknown record fields, empty/malformed IDs, missing contract fields, unsupported values, mismatched source assertions, duplicate source/species identities and inconsistent conflicts. Normalize whitespace/case, explicit IUCN aliases and ordering of list values only. No fuzzy species joins, unit conversion, stemming, ecological equivalence, range-to-abundance conversion or semantic matching occurs. Resolve synonym/units/taxonomy issues during reviewed extraction and retain the original record plus the transformation rationale in the provenance ledger. If sources conflict, mark conflicting rather than silently choosing one.

## Sampling and evidence variants

The pilot selector accepts only curator-verified membership in an India sampling frame with a published source URL and at least one ecological field. It performs seeded genus round-robin selection, records every exclusion and reports insufficient coverage when fewer than the requested approximately 30 species qualify. Existing taxonomy-only records qualify for **zero** pilot places. No ecological values or India membership are inferred from scientific names.

After selection, split species, optionally grouping all members of each genus, into train/validation/test before constructing examples. All pilot genera are designated developmental and excluded from final train/validation/test allocation when genus grouping is enabled. All variants remain together. The split file records seed, fractions, input hash and assignments. Dataset-building writes train/validation-only training input, separate partitions, an all-partitions private evaluation file, model-only payloads and review packets. Do not feed the combined file into training; the trainer rejects pilot/test partitions.

Complete includes all **collected** available fields, not all real-world knowledge. Partial masks a reproducible seeded subset of available fields using an explicitly configured fraction. Minimal masks all ecological fields, retaining scientific identity. A record with few available fields may have identical partial/minimal variants; retain and report that fact rather than inventing differences. The mask stores initially selected, dependency-masked and final withheld fields.

Visible payloads are whitelist projections: scientific identity, opaque evidence IDs, canonical structured values, and field-specific canonical evidence excerpts. Raw narrative excerpts, URLs, source titles, search queries, summaries, notes, hidden values, expected answers, split and mask metadata never enter model prompts. This conservative representation permits legitimate source traceability through the separate opaque-ID-to-original-record map. Direct echoes of withheld values in another field are masked recursively. Curators must check semantic dependencies that literal matching cannot detect and record their review before freezing; the software does not claim to solve semantic de-identification.

Expected targets are built **from each masked payload**, never copied from complete targets. Missing fields use `{value:null, kind:"unavailable", source_ids:[]}`. Available fields copy the reviewed value and supporting opaque IDs with `kind:"source_reported"`. Output has a required `draft_for_review:"draft_for_human_review"` marker. Free-text factual claims and suggested actions are separate arrays. Suggested actions are proposals for consideration; assertions embedded in them still require annotation. The deterministic target/template produces no free prose or proposals.

This initial contract deliberately measures structured evidence fidelity. Canonical excerpts are weaker than naturalistic source-text reasoning; add a separately versioned raw-excerpt condition only after audited masking and annotations support it. Never generalise structured extraction results to unrestricted report reasoning.

## Metrics

All stored metrics have numerator, denominator and value. A zero denominator is null, never zero or perfection. Primary JSON validity is strict: no fence removal/repair, no duplicate keys or non-finite constants. Schema compliance requires every field/type/abstention marker and correct identity. Truncation/execution failures make content unassessable even when a prefix happens to parse. Original relaxed-parser results remain separate.

| Metric | Numerator / denominator | Invalid/incomplete output |
|---|---|---|
| JSON validity | valid JSON responses / attempted responses | 0/1 |
| Schema compliance | full-schema, correct-identity responses / attempted responses | 0/1 |
| Assessable output | schema-valid, nontruncated, successful responses / attempts | 0/1 |
| Available reporting, end to end | correct supplied field values / available fields | zero numerator; full expected denominator |
| Correct abstention, end to end | null abstentions on absent fields / absent fields | zero numerator; full expected denominator |
| Structured field success, end to end | correct supported value+citation or correct abstention / all expected fields | 0/9 |
| Available reporting / correct abstention, assessable | same counts restricted to assessable outputs | excluded from conditional denominator; failure rate reported alongside |
| False abstention, assessable | abstained available fields / available fields on assessable outputs | unassessable, never labelled correct abstention |
| Unsupported structured claims | assertions lacking matching supplied field support / source-reported structured assertions | unassessable; never assumed zero unsupported claims |
| Citation existence | source-reported structured assertions with citations / structured assertions | unassessable |
| Citation validity | known evidence-ID citation occurrences / citation occurrences | unassessable |
| Structured citation support | citations matching associated field and normalized value / citation occurrences | unassessable |
| Prose citation validity | known IDs / prose citation occurrences | existence only; semantic support pending annotation |

No-claim outputs get null claim/citation denominators. A fully abstaining minimal-evidence report can have correct abstention 1 but has no available-evidence-use estimate. Empty output fails end-to-end. A true real-world value absent from supplied evidence is unsupported. Existing citation IDs can still fail associated-field support. Prose string similarity is never treated as entailment.

Tables provide micro counts and equal-species macro means: average defined variant values within species, then average species. They are different estimands; retain both. Species counts, assessable counts, failed runs and zero-denominator exclusions accompany results. Primary paired inference uses species clusters and complete method/seed grids, retaining all variants. Do not treat fields, variants or seeds as independent species.
