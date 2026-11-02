# Web-collected SoIB pilot draft

Collected on 20 October 2026 after discovering the official archive through web search. **30 source-backed species records and 150 field assertions are collected; human review remains pending.** No model was run. These records are not yet a verified or frozen pilot.

## Primary source and access

- State of India's Birds Partnership (2023), *State of India's Birds: Range, trends, and conservation status*, Zenodo v1: https://doi.org/10.5281/zenodo.11124590
- Archive metadata: `zenodo-record.json`. It lists `mit-license`; `LICENSE.txt` preserves the SoIB Partnership's notice from its official repository at commit `1ce6d0bf72f5a0bae46427ad5fb4686372f3b031`.
- National assessment table: https://zenodo.org/records/11124590/files/SoIB%202023%20India.csv?download=1
- Publisher README: `README.txt`, which identifies the CSVs as results for individual spatial extents.
- The downloaded India table matches published MD5 `45510848bbf006d404ea8d9aade91b81`. Local SHA-256, retrieval timestamps, byte counts and request URLs are recorded in `download_manifest.json`.

This is a **2023 assessment snapshot**, not a current 2026 assessment. A newer archive version is advertised, but was not substituted silently. Use the DOI/version and hashes when describing this collection. Only published aggregate classifications are imported; raw eBird observations and IUCN API records were not collected. The original CSV is retained locally for provenance and may contain columns not imported into model-visible evidence.

## Selection

The source table has 1,357 rows, of which 942 have `Selected for SoIB=TRUE`. Restrict to those rows, exclude scientific names exactly present in the original 100-record EcoPath experiment, and sample with seed 42 by round robin across the source's current-annual-trend categories. Require one species per genus until 30 species are chosen. This creates 30 distinct genera and intentionally varies published trend assessments.

This category-balanced developmental sample is not a representative estimate of Indian birds. Exact-name exclusion does not resolve historical taxonomic synonyms. The source's selection flag supplies evidence for sampling-frame membership, but the membership and extraction flags remain pending human review. The existing production pilot selector will not treat these flags as verified.

Full counts, exclusions and selected strata are in `collection_summary.json` and `sampling_exclusions.jsonl`. `selected_source_rows.jsonl` preserves the exact selected rows and row hashes. Record identifiers use **CSV data-record numbers**, starting with the first data record as 1, rather than assuming physical line numbers.

## Field mapping

| Contract field | Imported published classification |
|---|---|
| population_trend | SoIB 2023 long-term and current annual trend status, explicitly scoped to India and the assessment |
| range_summary | SoIB 2023 distribution range-size category; no conversion to abundance or a geographic range description |
| habitat | Habitat Specialization classification |
| diet | Diet Guild classification, preserving source labels |
| migratory_behavior | Migratory Status within India classification, preserving uncertainty |

`Insufficient Data`, `Trend Inconclusive` and `Uncertain` are reported as explicit source classifications; they do not become claims of stability, increase or decline. Quoting a source's uncertainty assessment is different from inventing a direction.

Global IUCN status, total population size, breeding behavior and species-specific threats remain null in this collection. National priority/regional Red List categories are not relabelled global IUCN categories. The `1% Population Threshold` column is not a total population estimate. Daily breeding activity period is not breeding phenology. Generic report-level threats are not assigned to individual species.

Each available field has its original column/value excerpt, URL, source record identifier, actual retrieval time, licence attribution, transformed value and `extraction_review=automated_pending_human`. Source excerpts and unimported columns remain outside model payloads. No hidden global-status value is supplied through source metadata in masked variants.

## Outputs and checks

- `pilot_records.DRAFT.jsonl`: 30 records in the existing evidence contract.
- `pilot_overview.csv`: compact species, genus, trend-stratum, availability and review overview.
- `extraction_review_queue.jsonl`: 150 source/value comparison cards with reviewer/decision fields empty.
- `provisional_variants.PRIVATE.jsonl`: 90 complete/partial/minimal variants with private expected values and provenance.
- `model_payloads.DRAFT.jsonl`: only the allowed model-visible projections.
- `composition.json`: species/taxonomic counts and evidence availability by level.
- `build_draft.py`: deterministic offline extraction script; exclusive output creation prevents silent replacement.

The builder checks the published checksum, validates every record, enforces 30 distinct genera, and rebuilds/validates all masking variants. An additional QA record checks source references and model-payload separation. These checks verify software and source consistency, not independent ecological truth or human annotation.

Before a frozen pilot: review the 150 extraction cards, check taxonomic membership and semantic masking dependencies, approve the source/version scope, and provide separate validation species for demonstrations. Only then explicitly update review flags in a **new reviewed dataset version**, retaining this draft. Keep a named review ledger. No reviewer labels or approvals have been fabricated here.

## Source-audit follow-up

The original draft above is preserved. Use [reviewed-v4](reviewed-v4/README.md) for the current audited snapshot: 120 species, 720 source assertions, and 360 variants across 30 development, 30 validation, and 60 test species. It includes a cross-check against SoIB's 2025 table, four taxonomy corrections, and the explicit global `IUCN Category` source field. Two IUCN category values differ between the 2023 and later table and remain dated rather than silently overwritten.

The audit was performed by a Codex AI assistant. It does not claim human ornithologist credentials or independent ecological field validation. India Checklist v10.1 and the SoIB 2026 workbook were identified but not reviewed; the newer SoIB record's inspected rights page did not expose a file-level licence. Keep the final test partition sealed and do not describe the data as current 2026 ecology.
