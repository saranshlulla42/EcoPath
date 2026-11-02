# EcoPath research and paper handoff

Updated 29 October 2026, 17:22 UTC. This is a handoff to an agentic coding assistant with access to the same computer and workspace. Treat the progress counts as a timestamped snapshot: inspect the live status before acting.

## User's objective and constraints

Complete a time-limited research-paper submission about QLoRA fine-tuning of Qwen2.5-7B-Instruct for evidence-bounded bird conservation report drafting in EcoPath. The user explicitly does **not** want to change the paper's purpose or title. They approved a shorter evaluation followed by edits to only the parts of their existing paper that absolutely need correction or new results. Preserve the original title, authors, purpose, fonts, figures, page geometry, and unaffected content. Deliver a visually verified PDF or DOCX, whichever best preserves the existing paper; the current workflow uses PDF because it retains the original pages and Times fonts.

The user expressly waived any additional human or expert review or sign-off. Do not ask for another expert. Clearly disclose that the new dataset source review was AI-assisted; do not claim credentials or invent expert validation. Do not invent positive QLoRA results, change the frozen comparison after seeing outcomes, or equate exact source matching with validated ecological truth. Report null, negative, or mixed results honestly.

The user requested reduced processing time. Do not resume the entire 1,260-output/seven-method grid for this submission unless they explicitly change the request.

## Workspace and context

- Workspace root: `/home/saranshlulla/Documents/Capstone`.
- Main project: `/home/saranshlulla/Documents/Capstone/ecopath`.
- User's paper: `/home/saranshlulla/Downloads/Paper 2nd draft.pdf` (12 pages, standard Times-Roman/Times-Bold/Times-Italic, 10.5-point main text). Preserve this original file.
- Historical experiment: `/home/saranshlulla/Documents/Capstone/ecopath_afterJudge-20260902T160124Z-1-001/ecopath_afterJudge`.
- The repository has many existing modified and untracked files, including user work. Do not reset, clean, overwrite unrelated files, or assume a clean Git checkout.
- Project context and ecological constraints: `ecopath/CLAUDE.md`; research overview: `ecopath/research/README.md`; data contract: `ecopath/research/docs/DATA_CONTRACT.md`; overall protocol: `ecopath/research/docs/PROTOCOL.md`. Be aware some old sections of `README.md`, `COMPLETION.md`, and `VERIFIED_PAPER_SECTIONS.md` describe earlier stages; use their dated updates and live artifacts for current status.
- The main project includes a FastAPI backend, Next.js frontend, conservation evidence contract and prompts, data collection, model training, evaluation, and paper artifacts. The paper's offline fixed-evidence evaluation is distinct from the live application's hybrid retrieval/heuristic/reporting service; do not attribute the latter's content or reliability solely to QLoRA.
- `*.PRIVATE.jsonl` files, source excerpts, model weights, and other large artifacts may be Git-ignored. Do not assume a Git-only clone contains the dataset, run log, adapters, or source PDF. Do not publish private material or credentials. If working on a different computer, securely transfer the original PDF, workspace including ignored research artifacts, legacy experiment, local model cache and runtime as needed, and provide a compatible GPU; this handoff alone does not contain all project files.

## Research evidence already established

The archived experiment in the original paper has 100 synthetic taxonomy-only examples, with 85 training species and 15 evaluation species, one adapter, and no separate validation set. The original saved raw outputs reproducibly contain valid JSON in 0/15 base responses and 15/15 adapted responses. Its historical purported schema check verifies six required key names, not field types or a full schema. The original prompt requests a structured report but does not explicitly demand JSON or provide a schema. The original judge used only the first 600 characters of the user prompt, generally omitting source results; its model identifier and teacher-judge independence are unverified. Consequently, the old judge scores do not establish evidence fidelity. The original data did not supply the principal ecological fields. See `research/docs/AUDIT.md` and `research/docs/PAPER_SECOND_DRAFT_REVIEW.md`.

Separately, the reviewed SoIB 2023 snapshot has 120 species split into 30 development/pilot, 30 validation and 60 test species, genus-disjoint, with complete, partial and minimal evidence variants. “Complete” means all six collected available fields, not a complete conservation assessment; population size, breeding and species-specific threats remain null. It is a dated dataset, not a source of automatically current conservation status. Three new QLoRA adapters (seeds 42, 43, 44) were trained and recorded, with validation checkpoint selection. They are separate from the historical adapter and dataset.

A four-condition development pilot completed 360 outputs (90 per method). Its separate summary is `research/artifacts/pilot-qwen-a09a354-v6/summary/`. Original, engineered, constrained, and deterministic template full-schema compliance were 0/90, 32/90, 88/90 and 90/90 respectively. Of 258 populated structured claims from constrained decoding, 41 matched corresponding reviewed source assertions under the automated comparison. These results are a development pilot, not the adapted held-out comparison or independent ecological ground truth.

## Authorized reduced comparison and live processes

The user agreed to compare the **unadapted constrained method** against **QLoRA seed 42 with the same schema constraints, evidence, prompt, demonstrations, pinned model/tokenizer, decoding and token budgets**, on all 60 held-out species with three evidence variants each: 180 outputs per method. The deterministic template arm already has 180 outputs. Other methods and QLoRA seeds were deferred for the deadline; one evaluated adapter seed cannot establish training-seed variation. The reduction was documented before either of these two test arms started in `research/docs/DEADLINE_EVALUATION_AMENDMENT.md`.

Use the existing frozen protocol, whose hash is `b0fc3242e40019a55578a50c2d10f8663d4e5f0eab32a9bdc448270aea9e7d79`:

- Protocol: `research/artifacts/final-qwen-a09a354-v1/protocol.json`.
- Dataset: `research/data_collection/soib2023-v1/reviewed-v4/all_variants.PRIVATE.jsonl`.
- Append-only output: `research/artifacts/final-qwen-a09a354-v1/run.jsonl` and its manifest and lock.
- Primary metric: equal-species end-to-end structured-field success; retain format failures, keep all three variants within each species, report 2,000 paired species-bootstrap draws, seed 42. Secondary metrics and caveats are specified in the amendment.

At 17:22 UTC on 29 October, latest saved rows were: template 180, original 62, `qlora-42` 46, constrained 0; no recorded execution errors. The original arm was deliberately interrupted with its rows preserved to prioritize this reduced evaluation. These counts will change.

At that snapshot two host processes were active: PID 153201 running `qlora-42`, and PID 153371 queued on the same run-file lock to run `constrained` after the first finishes. The jobs run in separate processes to fit the 8 GiB RTX 3070 Laptop GPU. At that snapshot a supervisor was also active (host PID 154311) running `research/paper_revision/finish_submission.py`; its status is `research/paper_revision/submission_status.json`. PIDs can change; do not rely on them without rechecking. Sandbox process namespaces may conceal host processes; inspect the host process list and GPU with appropriate permissions. **Do not launch duplicate GPU jobs or a second supervisor while these are running.** Closing the app, ending its sessions, sleeping the machine, or switching environments may terminate the processes; do not assume they will survive.

Check live status from the project root:

```bash
cat research/paper_revision/submission_status.json
pgrep -af 'research.cli run|research/paper_revision/finish_submission.py'
nvidia-smi
```

Progress is append-only; a JSONL reader should tolerate a partially written last line during an active append. The runner takes an exclusive file lock, validates frozen hashes, skips completed rows on resume, and explicitly preserves attempts. If a process is genuinely gone and an arm is incomplete, resume **only** that arm after checking the lock and GPU:

```bash
backend/.venv/bin/python -u -m research.cli run \
  --protocol research/artifacts/final-qwen-a09a354-v1/protocol.json \
  --dataset research/data_collection/soib2023-v1/reviewed-v4/all_variants.PRIVATE.jsonl \
  --out research/artifacts/final-qwen-a09a354-v1/run.jsonl \
  --execute-models --methods qlora-42
```

For the other arm, use the same command with `--methods constrained`, in a fresh process after the first has released the GPU. A queued process may already be waiting on the run lock. Do not blindly use `--retry-errors`: inspect failures first and retain their history. Process creation may require permission to access the host GPU, depending on your environment.

The measured mean time was about 30 seconds per QLoRA output in the early portion, and the previous constrained pilot was about 29 seconds per output; actual finish times can differ. At the snapshot, completion was likely still several hours away.

## Automated completion already prepared

The active supervisor waits until both prioritized arms contain all 180 outputs and have no execution errors. It then runs:

1. `research/paper_revision/collect_reduced_results.py` to produce `research/artifacts/final-qwen-a09a354-v1/reduced-summary/`, including `paper-evidence.json`, `paired-field-success.json`, metrics, and tables. It enforces the complete 60-species paired grid and the single seed.
2. The PDF artifact-operation marker required by the PDF skill in the current environment, then `research/paper_revision/build_minimal_revision.py`. It is designed to remove and replace only identified original PDF text operators, retaining original graphics and font names/sizes, and append a focused evaluation appendix. The intended output is `output/pdf/EcoPath_Paper_Minimal_Revision.pdf`, plus `output/pdf/minimal_revision_manifest.json`.
3. It sets `submission_status.json` to `pdf_generated_pending_visual_verification`; it does **not** claim final visual verification. Inspect `research/paper_revision/analysis.log` and `pdf_build.log` if status says `needs_attention`.

The scripts were prepared but the final two arms and the PDF had **not** completed at the handoff snapshot. Static replacements were checked to fit their original text boxes at the original font sizes; actual result-dependent abstract/conclusion layout and the completed appendix were not yet verified. The build may need a careful wording or implementation repair, especially if result-dependent text overflows. Preserve all genuine results and document every repair. Do not delete an existing summary or silently overwrite it if the supervisor partially succeeds; examine existing files and use an auditable new directory/name as appropriate.

After the PDF exists, execute the actual preservation verification:

```bash
/home/saranshlulla/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 \
  research/paper_revision/verify_minimal_revision.py
```

This renders source and revised pages to `tmp/pdfs/verification/`, compares original page geometry and image hashes, checks for pixel changes outside the documented edit rectangles, and checks visible fonts. Inspect the full-size renders of all edited pages and every appended page, including the contact sheet. Repair clipped text, spacing, table breaks, stale hidden text, extra page breaks, or unsupported claims; rerun verification after fixes. Do not deliver merely because the file exists. Independently inspect the results and wording against the saved summary and paired statistics; the document generator is prepared code, not proof of a correct outcome. Read the PDF skill instructions if available in your assistant environment and honor its artifact-operation and final-citation rules.

Finally deliver the actual verified PDF, with a concise description of the comparison, main observed result and material limitation (only one adapter seed evaluated). Make clear that the original paper's purpose and typography were preserved and that the new test is a disclosed deadline reduction. Never claim the remaining five arms were completed.

## User-facing instruction for a new assistant

“Please continue my EcoPath QLoRA experiment and minimal paper revision from `/home/saranshlulla/Documents/Capstone/ecopath/research/docs/OTHER_ASSISTANT_HANDOFF.md`. You have my authorization to inspect the whole project, keep the current GPU work running or resume incomplete work, run the matched comparison and analysis, and produce and visually verify the revised PDF. Keep the research purpose, title, fonts, figures and unaffected paper text intact, and only make necessary corrections. Do not ask for an additional expert review. Please check for the existing running jobs before starting anything, and report real results without overstating them.”

