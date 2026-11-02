# Reviewed SoIB dataset v4

This version adds the source's explicit `IUCN Category` field for all 120 species. It does not confuse that column with SoIB's India-specific `Priority Status` or the regional Red List field. The target retains the exact category string; its SoIB 2023 edition and retrieval scope are recorded in the private source assertion and dataset documentation.

A live comparison against the later SoIB 2025 India table found two differing table values: *Coracias benghalensis* is reported as Least Concern in the 2023 source and Near Threatened in the later table; *Pluvialis squatarola* is reported as Least Concern in 2023 and Vulnerable in the later table. The 2023 values are retained for this fixed-snapshot dataset; the differences are documented in `review_summary.json`.

Dataset design remains 30 development, 30 validation and 60 test species, genus-disjoint. Each has complete, partial and minimal variants. Population size, breeding behavior and species-specific threats remain null because the sources reviewed here do not support them. The test set must remain sealed.

This is a dated dataset review, not a current 2026 ecological reference. India Checklist v10.1 and a linked SoIB 2026 workbook have not been crosschecked. The reviewer is recorded as a Codex AI assistant; this is source extraction review, not independent field verification by an ornithologist. See `source_review_ledger.jsonl`, `taxonomy_crosswalk.jsonl`, and `review_summary.json`.
