# EcoPath evidence-fidelity study

Status (2026-10-29): the complete v6 GPU pilot (360 outputs) is scored; QLoRA seeds 42, 43, and 44 are trained; the frozen final test set is running. Template test outputs are complete, and the original GPU baseline is running. Expert ornithologist sign-off is waived by study decision and will not be sought. See [completion report](docs/COMPLETION.md) for results and remaining work.

The current source-audited dataset version is [reviewed-v4](data_collection/soib2023-v1/reviewed-v4/README.md): 120 species (30 development, 30 validation, 60 test), 720 dated source assertions, and 360 complete/partial/minimal variants. It includes a documented taxonomy crosswalk and the explicit SoIB 2023 global IUCN Category field. The reviewer ledger identifies the review as AI-assisted source checking. Expert sign-off is explicitly waived; results must not be described as expert-validated. The 2026 SoIB download and the latest India Checklist v10.1 have not been incorporated. No QLoRA superiority claim is supported.

Start with [the audit](docs/AUDIT.md), [data contract](docs/DATA_CONTRACT.md), [experiment protocol](docs/PROTOCOL.md), [annotation guide](docs/ANNOTATION.md), and [paper revision map](docs/PAPER_REVISION_MAP.md). [Completion report](docs/COMPLETION.md) distinguishes extraction, software checks, executed diagnostics and outstanding experiments.

Run from `/home/saranshlulla/Documents/Capstone/ecopath`. Existing code and large weights were preserved through `artifacts/original/manifest.json`, containing SHA-256 references and the pre-change Git revision. No weights were copied. Files ending `PRIVATE` and the blinding key must stay outside model prompts and training targets.

```bash
# No network, credentials or GPU; system Python already has pytest/jsonschema.
python3 -m pytest research/tests -q
python3 -m research.cli smoke --out research/artifacts/my-smoke-v1

# Project environment supports real tokenizer/parser checks without model inference.
ECOPATH_CONSTRAINT_TESTS=1 backend/.venv/bin/python -m pytest research/tests -q

# Read-only re-audit and taxonomy-only template diagnostic; use new destinations.
python3 -m research.cli audit --out research/artifacts/my-original-audit-v1
python3 -m research.cli legacy-template --audit-dir research/artifacts/my-original-audit-v1 --out research/artifacts/my-legacy-diagnostic-v1
```

Actual saved runs are under `artifacts/synthetic-smoke-v2` and `artifacts/legacy-template-v2`. These are fixture and taxonomy-only deterministic diagnostics, respectively. Neither is the proposed ecological pilot. `original/audit` contains recomputed structural counts and the original species/split inventory. Tokenizer diagnostics are CPU reconstructions, not new model outputs.

For a legitimate curated India frame in the contract:

```bash
python3 -m research.cli select-pilot --records curated-records.jsonl --count 30 --seed 42 --out pilot-selection.json
python3 -m research.cli build --records curated-records.jsonl --pilot-selection pilot-selection.json --seed 42 --validation-fraction .2 --test-fraction .2 --partial-fraction .5 --out dataset-v2
```

The fractions and seeds above are proposed engineering settings, not ecological thresholds. They must be reviewed using development coverage and frozen before final evaluation. A pilot-only collection is allowed. Independent development and final species require an expanded frame; do not reuse pilot genera as final test genera.

Copy `configs/comparison.proposed.json` and fill the immutable base/tokenizer revision, validation demonstration IDs, and verified adapter paths. The proposed file deliberately cannot execute as-is. For the baseline pilot, remove pending QLoRA methods; retain original, engineered, constrained and template. Train only if the baseline pilot and human labels justify adaptation.

```bash
backend/.venv/bin/python -m research.cli freeze --config comparison.local.json --dataset dataset-v2/examples.PRIVATE.jsonl --out pilot-protocol.json
backend/.venv/bin/python -m research.cli run --protocol pilot-protocol.json --dataset dataset-v2/examples.PRIVATE.jsonl --out pilot-run.jsonl --execute-models
python3 -m research.cli summarize --run pilot-run.jsonl --out pilot-tables
python3 -m research.cli annotate --run pilot-run.jsonl --dataset dataset-v2/examples.PRIVATE.jsonl --out pilot-review --seed 42
python3 -m research.cli adjudicate --reviews reviewer-one.jsonl reviewer-two.jsonl --out adjudication.jsonl
python3 -m research.cli annotation-summary --adjudication adjudication.jsonl --out human-summary.json
python3 -m research.cli statistics --run pilot-run.jsonl --dataset dataset-v2/examples.PRIVATE.jsonl --method-a constrained --method-b qlora --metric structured_field_success_e2e --draws 2000 --seed 42 --out paired-statistics.json
```

Training command (only train/validation partition; cached weights and CUDA required):

```bash
backend/.venv/bin/python -m research.train --config training.local.json --dataset dataset-v2/training.PRIVATE.jsonl --out research/training --execute
```

`configs/training.proposed.json` declares three seeds. Runtime package versions, adapter provenance, failed runs, validation checkpoint selection, time and memory scope are recorded. No script provisions compute, calls a paid model API or downloads weights. Install optional GPU packages in a vetted environment and preserve its exact environment lock; the local tokenizer/constraint environment is recorded in `artifacts/validation/environment.json`. Full GPU compatibility remains unverified until opt-in generation/training succeeds.

To reproduce the original prompt condition on a prepared GPU host, run the preserved `run_evaluation_hf.py` against the preserved `splits/eval.jsonl`, supplying `--base-model` as a local snapshot at the chosen immutable revision, `--adapter-dir` as the preserved adapter, and a **new** `--output`. Its defaults are 1024 new tokens and temperature 0.1, not verified effective settings of the saved run. Preserve external timing, hardware, revision and CLI records. A newly pinned revision is a reconstruction choice because the original immutable revision is unavailable.

The live app keeps its existing report default. The species report panel also accepts `dataset-v2/review_packets/*.json` for fixed-evidence method previews. Its local Ollama exports are an operational preview; they do not substitute for the frozen HF comparison. Configure `OLLAMA_COMPARISON_BASE_MODEL` and the existing `OLLAMA_REPORT_MODEL`. The new endpoint does no retrieval. Legacy live drafts visibly carry unverified status.

Generate the audit figures with `backend/.venv/bin/python -m research.plots --audit-dir research/artifacts/original/audit --out research/artifacts/my-figures-v1` (Matplotlib required). Do not reuse an existing output directory containing figure files.
