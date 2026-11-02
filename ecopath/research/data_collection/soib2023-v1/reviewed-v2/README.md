# Source-audited SoIB dataset v2

The original pilot's 150 extraction cards were checked against their exact rows in the checksum-verified Zenodo SoIB 2023 India CSV. The ledger names the reviewer as a Codex AI assistant and states the scope: source-faithful transcription and field mapping, not independent ecological expertise. No ecological claims beyond the table are added.

This version contains the 30 development pilot species and 30 validation plus 60 final-test species, selected outside the pilot and the original 100-record experiment. The 90 held-out species have distinct genera and are divided before variant construction (seed 9173); each has complete, partial, and minimal views. Keep the test partition sealed until the protocol and model are frozen.

All records remain restricted to the 2023 SoIB snapshot. `heldout_model_payloads.jsonl` contains model-visible projections; `heldout_variants.PRIVATE.jsonl` contains private expected values and provenance. `source_review_ledger.jsonl` is the assertion-level review record.

Independent ornithologist review is still required before representing these labels as ecologically validated. The review process did not resolve historical synonyms. See `review_summary.json` for details.
