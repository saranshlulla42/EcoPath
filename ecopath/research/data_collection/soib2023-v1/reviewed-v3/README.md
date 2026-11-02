# Source-audited dataset v3

This version retains the 2023 SoIB source rows and their field provenance, checks the 600 ecological assertions for the 120 pilot/held-out species against the publisher's SoIB 2025 national table, and applies four documented taxonomy corrections. No ecological field mismatches were found. The publisher states that 2025 keeps the same 2023 trend and range status categories while updating the underlying observation-based graphs/maps.

Three accepted scientific names are updated: *Charadrius alexandrinus* → *Anarhynchus alexandrinus*, *Mirafra assamica* → *Plocealauda assamica*, and *Cholornis unicolor* → *Paradoxornis unicolor*. The SoIB 2025 table also corrects Little Swift order to Apodiformes and Brown Parrotbill family to Paradoxornithidae. Original SoIB names remain recorded for traceability; stable species IDs and source-row record locators are preserved.

This is taxonomy as published in the SoIB 2025 table, not a claim to the latest 2026 taxonomy. India Checklist v10.1 and a linked SoIB 2026 workbook were identified but not crosschecked. The reviewer is a Codex AI assistant: this is a source-consistency and taxonomy audit, not human credentials or independent field verification. The 2025 Zenodo record's visible rights section does not state a file-level license; do not redistribute the full 2025 CSV without clarifying its reuse terms.

There are 30 development, 30 validation, and 60 held-out test species, with no species/genus overlap after taxonomy updates. Keep test targets in `heldout_variants.PRIVATE.jsonl` sealed until the model and protocol are frozen. See `review_summary.json` and `taxonomy_crosswalk.jsonl`.
