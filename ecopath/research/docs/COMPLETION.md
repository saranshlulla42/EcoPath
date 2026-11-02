# Completion report — 20 October 2026

The available repository work is implemented and checked. **Whether QLoRA improves evidence fidelity remains unanswered.** The available original experiment supports a formatting difference under its weak prompt; it cannot establish the requested ecological-fidelity claim.

## 1. Extracted and verified

- Original dataset: 100 unique species, 31 families and 16 orders; preserved 85/15 species split. No species overlap, but Larus/Turdus genus overlap. No separate validation record.
- All recorded ecological fields are missing for all 100 species. All 100 evidence items are GBIF taxonomy snippets. India sampling membership, original selection/exclusions, retrieval dates and exact teacher configuration are unavailable.
- Saved outputs reproduce **0/15 base and 15/15 adapted strict JSON validity**. The original “schema” result is required-key presence. Full source/field fidelity was not measured.
- Training role markers differ from the saved tokenizer's native template. Saved-tokenizer reconstruction finds no duplicate-special-token difference in the original evaluation path, and no sample exceeds the script's 4096-token default. This does not recover unknown effective original run settings.
- Recorded adapter/TrainingArguments/trainer-state values are extracted, distinguishing saved values from code defaults. The local and archived adapter weights match. Original duration, GPU hours, memory, hardware and immutable base/tokenizer revision remain unavailable.
- The original judge used a prompt prefix generally omitting actual search results. Scores remain supplementary; human validation/independence is not established.
- A SHA-256 manifest preserves original references without copying weights. The final integrity check confirms **69 original experiment/tokenizer/adapter files unchanged**. Existing unrelated repository changes were retained.

## 2. Implemented and tested

- Shared evidence/output contracts; provenance validation; explicit null/conflict semantics; recognized source-quoted IUCN categories.
- Reviewed India-frame eligibility and genus-aware pilot selection, species/genus splits before examples, deterministic complete/partial/minimal variants, direct-echo masking, targets rebuilt from visible fields, and separate private references/training partitions.
- Original, engineered, constrained, QLoRA, deterministic template, and secondary unconstrained-QLoRA runners. Engineered conditions share prompt/evidence; constraints/adaptation differences are recorded.
- Frozen protocols include full small-source snapshots, hashes, exact settings, planned examples, environment and adapter provenance. Runs validate hashes/environment, lock writes, append individual results, preserve errors/attempts and resume without duplicates.
- Native-template assistant-only training path with validation checkpoint selection and three independent proposed seeds. It is implemented, not GPU-validated.
- Strict/schema/field/abstention/citation metrics, end-to-end and assessable rates, zero-denominator behavior, per-species aggregation, paired species/seed bootstrap, per-seed/level/configuration/cost/error tables.
- Blinded v2 and original-output review exports, explicit label origins, disagreement/adjudication records and completed-human-annotation summaries. Human labels have not been supplied.
- Fixed-evidence application preview with configurable methods, source/missingness display, supported structured-value checks, false-abstention warnings, token-limit/invalid response handling and draft labels. The existing live report method remains the default and is visibly unverified; its source-reported category display no longer takes an unsupported model category.
- Audit, contract, protocol, annotation guide, official-source notes, verified manuscript replacement text, paper revision map and architecture diagram. The methodology source was revised; the historical platform report carries an audit notice.

Validation records are in `../artifacts/validation/`:

| Check | Actual outcome |
|---|---|
| Research pytest suite including real schema parser and saved-Qwen token filtering | **39 passed, 1 skipped**; skipped test requires explicit cached-model/GPU opt-in |
| Backend tests and existing report-parser regression checks | **48 passed** |
| Entire existing frontend Vitest suite plus new rendering tests | **107 passed** across 11 files |
| Focused frontend lint | passed |
| Full frontend TypeScript check | failed on generated `.next/dev/types`, existing TimelineScrubber mock types, missing `@supabase/ssr` and associated implicit-any errors; no diagnostics in the new preview component/test |

The current Python environment emits existing Python 3.14/pytest-asyncio deprecation warnings; these are recorded in the test summaries. New CPU dependency installation was limited to validation/plotting packages in the project virtual environment. `environment.json`, `python-packages.json` and `requirements-observed.txt` describe the current check environment, **not the original training environment**.

The packaged LM Format Enforcer Transformers integration failed against the installed Transformers 5 tokenizer import. A small bridge using its public token-enforcer API fixed the integration; actual Qwen token-by-token constraints then passed. An initial synchronous TestClient route check stalled in this environment; an asynchronous in-process ASGI transport passed without network or application startup. Intermediate diagnostic failures are retained or described; they were not counted as model experiments.

## 3. Experiments and diagnostics actually executed

| Phase | Executed work | Meaning |
|---|---|---|
| Original-record audit | Re-scored 30 saved responses from 15 paired species; exported 30 blinded packets; generated structural/bootstrap and error artifacts | Saved-output analysis, no new generation |
| Original tokenizer diagnostic | CPU tokenization/template/length checks with saved tokenizer | Reconstructed token diagnostics, not original generation telemetry |
| Synthetic fixture, current v2 | **9 invented identities × 3 variants = 27 deterministic outputs**, with masks, raw/parsed results, timings, tables and annotation packets | Offline pipeline smoke test; explicitly non-ecological fixture values |
| Legacy taxonomy diagnostic, current v2 | **100 original identities × 3 variants = 300 deterministic outputs** | Correct null behavior on all-missing fields; available-field use/citation support have zero denominators and remain undefined |
| Coverage check | **0 eligible of 30 requested pilot species** from the archived material | Real evidence collection and verified India membership are required |

Current runs are `synthetic-smoke-v2` and `legacy-template-v2`. Their source snapshots/hashes verify and resume cleanly. Earlier v1 scaffolding diagnostics and the erroneous first tokenizer diagnostic are explicitly superseded in `diagnostic_index.json`. Do not use those intermediates as final results.

The deterministic synthetic run scores 243/243 end-to-end field decisions; the legacy diagnostic scores 2700/2700 abstentions. These are contract checks with known inputs, not evidence that any language model improved. No-claim rates remain undefined for claim support. The original paired species bootstrap has a degenerate [1,1] difference interval for JSON rate because every pair differs identically; it is conditional on this setup and does not demonstrate population certainty or fidelity.

Three PNG/SVG figures were generated from saved records and visually inspected: original JSON counts, ecological-field missingness and the three logged training-loss observations. No new model-performance, GPU-cost or human-fidelity figure was fabricated.

## 4. Remaining work: GPU, data, credentials and output annotation

- No working CUDA driver and no cached Qwen base weights. **No new base/QLoRA generation, reproduction, fine-tuning or live Ollama test was executed.** The installed ML packages alone do not resolve this.
- Curate legitimate ecological evidence with dated/licensed field extractions, a verified India frame and documented exclusions. The original taxonomy-only records cannot populate the ecological pilot. Review full current source terms and obtain IUCN/other authorised access where required; no new external data integration or restricted-record redistribution was attempted.
- Pin actual base/tokenizer commits, prepare a vetted cached model environment, choose validation demonstrations and document pilot decisions. Pilot/final configurations deliberately reject unavailable provenance/revisions and unfinished adapters.
- Run stronger pilot baselines, complete human annotations and determine whether adaptation is justified. Only then run the proposed three-seed training and freeze an untouched final evaluation.
- Complete investigator review of masking dependencies, annotation segmentation/agreement, sampling/precision rationale, AI-use/data-access statements and novelty claims. A focused literature/novelty review remains pending.
- Resolve the unrelated frontend type errors before claiming a clean production build.

**Expert ornithologist sign-off is waived by study decision (2026-10-29); it is not pending.** The completed source and taxonomy pass is an AI-assisted audit. It may be reported as source-checked against the cited SoIB tables, but not as expert-validated or independent ecological field verification. No additional expert reviewer is being sought.

No paid model API, paid compute provisioning, ecological retrieval workload or external message was launched. Exact runnable commands and blocked prerequisites are in `../README.md` and `PROTOCOL.md`.

## 5. Paper claims currently supported

Supported: the implemented architecture as code, the audited dataset/split/training records, the original saved-output formatting difference and the observed software-check outcomes. Reports are decision-support drafts requiring human review.

Not yet supported: improved evidence fidelity, correct use of available ecological evidence, conservation/category prediction accuracy, independent/validated judging, human usefulness, reduced cost, robustness across training seeds, Indian-bird generalisation, statistical superiority to strong controls, or novelty/absence of prior work. Keep these results visibly pending and report negative or mixed outcomes when real comparisons are complete.

## Subsequent web-collection follow-up

Web search located the official SoIB 2023 Zenodo archive. A published India assessment table was downloaded and matched to its publisher checksum; source metadata, MIT licence attribution and actual retrieval timestamps were saved. `research/data_collection/soib2023-v1/` now contains 30 source-backed draft species in 30 genera, 150 extracted assertions, a review queue and 90 provisional evidence variants. These are dated aggregate classifications, not current 2026 ecological assessments. Extraction/sampling human-review flags remain pending and no model generation was run. This advances data collection; the original archive's zero-coverage finding remains unchanged. See the collection README for selection, transformations and limitations.

## Source-review follow-up (2026-10-29)

`data_collection/soib2023-v1/reviewed-v4/` is the current source-audited snapshot: 120 species, genus-disjoint as 30 development / 30 validation / 60 test; 720 field assertions; 360 complete/partial/minimal examples. All 600 original ecological assertions were compared with the official SoIB 2025 national table. No category-field mismatches were found. The source publisher says the 2025 release retains the 2023 status categories while refreshing model-based trend/range data through 31 May 2025. Four taxonomic corrections are recorded (three accepted binomials and the order/family corrections for Little Swift and Brown Parrotbill). The explicit 2023 IUCN Category column was added and kept as a dated snapshot; two species differ in the 2025 table. Population size, breeding behavior and key threats remain missing rather than inferred.

This is a source-transcription and taxonomy audit by a Codex AI assistant, not an independent review by a credentialed ornithologist. Expert sign-off was explicitly waived on 2026-10-29 and is not a pending task; the limitation must remain explicit in any paper. The official India Checklist v10.1 and SoIB's linked 2026 workbook were identified but not reviewed; the 2025 table's visible Zenodo rights section did not state a file-level licence. Resolve rights before redistributing the newer source material.

## GPU execution update (2026-10-29)

The preceding status describes the state before the user prepared a GPU. The pinned public Qwen2.5-7B-Instruct snapshot (`a09a35458c702b33eeacc393d103063234e8bc28`) is now cached locally and checksum-verified. A local RTX 3070 Laptop GPU with 8 GiB VRAM is available. A 4-bit NF4 load and short generation smoke check succeeded.

Two frozen pilot attempts are retained as technical diagnostics, not model results. The v2 automatic device map left quantized layers on CPU/disk and failed on the engineered and constrained conditions. The v3 explicit CUDA device map loaded the model, but those same conditions ran out of VRAM under the 1,400-token generation cap. The original weak-prompt and deterministic-template rows did run; v3 must not be interpreted as a complete comparison.

A v4 feasibility protocol, `artifacts/pilot-qwen-a09a354-v4/protocol.json`, preserved the same 30 pilot species and four conditions with an explicit CUDA device map and a 768-token output cap, but kept two few-shot demonstrations. It completed all 360 rows; all 90 engineered and 90 constrained rows failed during warmup with OOM, while original and template completed. It is a technical failure, not a comparison.

The full prompt audit showed why the earlier short smoke did not predict v4: the frozen demonstrations expand the longest engineered input to 3,972 tokens. A one-demonstration prompt is 3,565 tokens. V5 (`artifacts/pilot-qwen-a09a354-v5/protocol.json`) kept the same species, split, model, four methods and 768-token cap while reducing demonstrations from two to one. Longest-prompt smoke generations for engineered and constrained conditions completed within the 8 GiB GPU and ended before the cap. In the full single-process run, however, both structured conditions again failed at warmup with OOM after the original condition. V5 is preserved as a process-level technical failure.

The v6 runner adds an explicit `--methods` filter so each condition can be run in a fresh process while appending to one protocol-homogeneous JSONL. V6 (`artifacts/pilot-qwen-a09a354-v6/protocol.json`) uses the same one-demonstration, 768-token condition as v5 and includes the runner change in its code snapshot/hash. Its first method is now executing; use v6 outcomes only after all four conditions complete. This fresh-process execution is part of the frozen procedure and does not change prompt content between methods.

QLoRA training, output annotation (AI-assisted, not credentialed expert review), and held-out test evaluation have not started. The training partition has 180 examples; native-template assistant-only sequences reach 3,144 tokens, so the configured 4,096-token budget avoids truncation. Expert sign-off remains explicitly waived; this does not convert AI-assisted source auditing into independent expert validation. The newer SoIB and India Checklist materials still require rights review before redistribution.

## Pilot and QLoRA execution update (2026-10-29)

The v6 pilot is complete: 360/360 outputs across original, engineered, constrained and deterministic-template conditions (90 each), all under protocol hash `2c5730a560319a388ac1fd9678350e8a60679bc064174c83fa6729c775e2f009`. The completed run has no execution errors. Forty original-prompt and two constrained outputs reached the 768-token generation cap. The original condition produced 0/90 schema-valid outputs; engineered prompting produced 32/90; constrained decoding produced 88/90; and the template produced 90/90. Among 258 non-null structured claims from constrained decoding, 41 matched the corresponding cited reviewed assertion (15.9%). This automatic match measures agreement with this dataset's reviewed extraction; it is not an independent ecological truth or expert judgment. The template result confirms contract construction, not model quality. Full tables and metrics are in `artifacts/pilot-qwen-a09a354-v6/summary/`.

The first two training attempts failed on the 8 GiB GPU. The recorded cause was memory pressure from fp32 conversion of the frozen vocabulary embedding/output head and full-sequence logits. The trainer now keeps frozen base weights in fp16, uses non-reentrant gradient checkpointing, and computes loss only on assistant-token positions. A compact training-only schema summary reduced full native-template sequences from a maximum of 3,144 to 1,573 tokens while preserving every evidence payload and target; there is no truncation. The change is frozen in the v4 training artifacts/config.

QLoRA seed 42 completed 36 optimizer steps and three validation passes; best validation loss `2.5038e-05`, training time 1,304.9 seconds. Seed 43 completed in an isolated process; best validation loss `3.8675e-05`, training time 1,335.6 seconds. Seed 44 is running in its own process because sequential seeds in one Python process retained GPU memory. Seed 42's adapter is in `artifacts/training.qwen-a09a354-v4/seed-42/selected_adapter/`; seed 43's adapter is in `artifacts/training.qwen-a09a354-seed43/seed-43/selected_adapter/`.

The final 60-species test protocol has been prepared as `configs/comparison.final.qwen-a09a354.json`, but is not yet frozen or executed. After seed 44 completes: freeze that config against `data_collection/soib2023-v1/reviewed-v4/all_variants.PRIVATE.jsonl`; run each method in a fresh process to fit GPU memory; summarize the 1,260 expected rows; and compute the preregistered species-level paired statistics. The constrained test arm will be the longest phase. No superiority claim is supported until those held-out results are complete. Expert sign-off remains waived; the source and dataset review is AI-assisted, not credentialed ornithologist validation.

## Held-out execution update (2026-10-29)

All three QLoRA seeds completed. Best validation losses were 2.5038e-05 (seed 42), 3.8675e-05 (seed 43), and 2.3243e-05 (seed 44). The final protocol is now frozen at `artifacts/final-qwen-a09a354-v1/protocol.json`, hash `b0fc3242e40019a55578a50c2d10f8663d4e5f0eab32a9bdc448270aea9e7d79`, with the reviewed-v4 dataset hash and all seven methods. Its planned grid is 1,260 outputs (60 test species × 3 evidence variants × 7 methods). The deterministic template test arm completed all 180 rows. The original GPU baseline has started in a fresh process; further methods will be run one method per process to avoid cross-method GPU memory retention. Held-out evaluation and paired analysis remain pending until the grid is complete.
