# Review of the second paper draft

Reviewed 29 October 2026. Original PDF: [second draft](</home/saranshlulla/Downloads/Paper 2nd draft.pdf>). This review compares the manuscript with saved local research artifacts. It does not verify the bibliography against external publications or certify compliance with a submission venue's rules.

## Recommended submission scope

Revise the existing manuscript as a feasibility study with two explicitly separate experiments:

1. **Archived QLoRA experiment:** 100 taxonomy-only synthetic examples; 85 training species and 15 evaluation species; one saved adapter. Retain the reproducible JSON counts of 0/15 base and 15/15 adapted. Interpret these as a formatting difference under the original prompt.
2. **Controlled prompting pilot:** 30 development species, each with three evidence variants, evaluated with four methods; 360 saved outputs. Report full-schema compliance and agreement with reviewed structured source assertions, with the limitations of those checks.

The experiments use different datasets, report contracts, and adapters. Do not pool their counts or treat the second experiment as a controlled comparison with the archived adapter. The newly trained three-seed QLoRA adapters have not completed the frozen held-out comparison.

Suggested title: **Structured Bird Conservation Report Drafting in EcoPath: QLoRA Feasibility and a Controlled Prompting Pilot**.

The complete seven-method held-out grid can support a later revision. At inspection, its saved log contained 180 template and 36 original-prompt outputs, with no recorded outputs for the remaining methods. These partial counts are a progress snapshot, not a result table. The log advanced during inspection; a sandbox process listing did not establish whether background inference was running.

## Corrections in submission priority order

| Location in PDF | Finding | Required wording or action |
|---|---|---|
| Abstract; Sections 3.5 and 4.2; Tables 3 and 4 | The archived function called `check_schema` checks six key names and permits either of two layouts. It does not validate field types or a full JSON schema. | Replace the archived metric label with **required-key presence**. Preserve the separately reproduced JSON counts. Reserve **full-schema compliance** for the new pilot's actual schema validator. |
| Section 3.5; Section 4.2; Figure 3; Section 5.1 | The historical judge received only `prompt_user[:600]`. The source-result section generally appears later. The statement that the judge assessed reports against the supplied evidence is too strong. | Disclose the context truncation. Remove judge grounding/usefulness means from the abstract and the main evidence-fidelity argument. If retained, place the historical ratings in a supplementary table with the context flaw stated in its caption. |
| Section 4.2; Table 3; Section 5.1 | The archived prompt requests a structured report but does not explicitly request JSON, specify the schema, or provide demonstrations. Calling the base prose a failure to produce the requested JSON objects overstates the instruction it received. | State that the adapted model produced the learned JSON layout under a general structured-report instruction. Explicitly identify the baseline as weak for testing whether adaptation is necessary for JSON. |
| Abstract; Section 3.3 | The draft says target reports identify evidence gaps. The source audit also found heuristic risk language unsupported by taxonomy-only inputs. | Describe the targets as synthetic drafting examples, with incomplete teacher provenance and some unsupported risk language identified during audit. Do not describe them as verified conservation reference reports. |
| Section 3; Section 4; Section 5.5 | The current prose describes only the archived experiment. The new dataset, completed pilot, and new training runs are absent. | Add a separate follow-up experiment subsection. Keep historical limitations attached to the historical experiment; record which gaps the new design addresses and which empirical questions remain open. |
| Section 5.5; Figure 3 | The exact historical judge identity is not established by the saved label. The chart still prints the unverified model label prominently. | Use an explicitly unverified historical judge label if retaining the figure, or replace the figure with the completed pilot's deterministic metrics. Do not substitute a guessed provider identifier. |
| Section 3.3; limitations | The historical split is species-disjoint but shares the genera Larus and Turdus. | State the genus overlap. Describe genus separation only for the new 120-species dataset. |
| Abstract and conclusion | Structural outputs and automated ratings do not establish conservation correctness or reviewer benefit. | Restrict conclusions to formatting feasibility, measured structured-field behavior, and the need to evaluate QLoRA's incremental value under matched evidence and output requirements. |

## Completed pilot table suitable for a separate results subsection

Each method was run on the same 30 development species under three evidence variants: 90 outputs per method. These are development-pilot results, not held-out final-test results.

| Method | Valid JSON | Full-schema compliant | Outputs at generation cap |
|---|---:|---:|---:|
| Original instruction | 0/90 | 0/90 | 40/90 |
| Engineered prompt | 90/90 | 32/90 | 0/90 |
| Constrained decoding | 88/90 | 88/90 | 2/90 |
| Deterministic template | 90/90 | 90/90 | Not applicable |

All conditions share a 768-token generation cap. Report truncation alongside structure: the two constrained failures reached that cap. The template copies supplied structured values by construction; its results demonstrate contract behavior rather than a learned ecological capability.

For constrained decoding, 41 of 258 populated structured claims matched their corresponding reviewed cited assertions under the automated comparison. This is **15.9% exact structured-source agreement among populated claims**, not an independently assessed ecological factuality score. Citation identifiers can exist and refer to the expected field while the generated value still differs from the source assertion. Differences require care because automated matching does not establish semantic entailment or adjudicate paraphrases.

The pilot's minimal-evidence condition contains missing fields. Success there can reflect appropriate null outputs; it does not establish supported extraction when facts are available. Keep the complete/partial/minimal breakdown in a supplementary table. Do not treat the 90 outputs as 90 independent species; variants share a species.

## Suggested replacement abstract

Preparing bird conservation report drafts from incomplete information requires consistent structure and a clear account of what the supplied evidence supports. We investigated these requirements in EcoPath through an archived QLoRA experiment and a separate controlled prompting pilot. The archived experiment adapted Qwen2.5-7B-Instruct using 85 synthetic, taxonomy-only examples and evaluated 15 additional species. Re-analysis found valid JSON in 15/15 adapted responses and 0/15 base responses; however, the original instruction did not explicitly require JSON, and the structural check established required-key presence rather than full schema validity. A follow-up pilot used 30 development species with three evidence variants each, drawn from a separately curated 120-species, genus-disjoint dataset. Across 90 outputs per method, full-schema compliance was 0/90 for the original instruction, 32/90 for engineered prompting, 88/90 for constrained decoding, and 90/90 for deterministic construction. Among 258 populated claims from constrained decoding, 41 matched the corresponding reviewed source assertions under automated comparison. These findings establish formatting feasibility and show that structural compliance alone does not establish agreement with supplied evidence. The incremental value of the newly trained QLoRA adapters remains unresolved pending completion of the frozen held-out comparison. The work supports a narrowly scoped drafting application and an auditable evaluation design rather than a validated conservation assessment.

## Suggested replacement limitation for historical judging

Historical LLM ratings were generated from a prompt prefix limited to 600 characters, which generally omitted the source-result section. These ratings cannot establish fidelity to the complete supplied evidence. The effective historical judge identity and teacher-judge independence are also unresolved. Accordingly, these scores are retained only as archival descriptive observations and are excluded from the main evidence-fidelity conclusions. Dataset source review for the follow-up study was AI-assisted and does not constitute independent ornithologist validation. No additional expert sign-off is being represented as completed or required by this revision.

## Suggested conclusion

The archived experiment demonstrates that QLoRA can establish a learned JSON reporting pattern under the tested taxonomy-only instruction. A separate controlled pilot shows that explicit prompting and constrained decoding can also improve structural compliance, while agreement between populated outputs and reviewed source assertions remains a distinct challenge. These experiments do not yet establish an incremental benefit of QLoRA under matched contemporary baselines. EcoPath provides an implementation and evaluation setting for that comparison, with explicit missingness, source associations, and a frozen held-out protocol.

## Submission work that can proceed without further GPU inference

1. Correct the archived metric names and weak-baseline description throughout the PDF, including abstract, tables, captions, and appendix.
2. Move the flawed-context historical judge scores out of the abstract and main evidence-fidelity argument.
3. Add the completed prompting pilot as a separate experiment using the table and denominator explanations above.
4. Describe the new dataset as a fixed SoIB 2023 snapshot, with 120 species, 30 development/30 validation/60 test species and three evidence variants; identify AI-assisted extraction review and source provenance. Do not imply that dated categories are current assessments.
5. Describe the completed new adapter training separately from the uncompleted held-out comparison. Low validation token loss is not a measured gain in evidence use.
6. Include exact protocol/model revisions and links to reproducible artifacts for the new work. Mark unavailable historical details explicitly.
7. Apply the venue's page limit, reference style, anonymization, and AI-use rules once those requirements are known. Prepare a data/code availability statement that respects the recorded source access and redistribution terms.

This review does not require another expert reviewer and does not invent an expert evaluation. Submission acceptance and venue compliance cannot be inferred from the experimental artifacts alone.

## Local evidence used

- [Archived experiment audit](/home/saranshlulla/Documents/Capstone/ecopath/research/docs/AUDIT.md).
- [Archived evaluation prompt and inference code](/home/saranshlulla/Documents/Capstone/ecopath_afterJudge-20260902T160124Z-1-001/ecopath_afterJudge/scripts/run_evaluation_hf.py).
- [Archived key check and truncated judge context](/home/saranshlulla/Documents/Capstone/ecopath_afterJudge-20260902T160124Z-1-001/ecopath_afterJudge/scripts/grade_results.py).
- [Completed pilot summary](/home/saranshlulla/Documents/Capstone/ecopath/research/artifacts/pilot-qwen-a09a354-v6/summary/summary.json) and [tables](/home/saranshlulla/Documents/Capstone/ecopath/research/artifacts/pilot-qwen-a09a354-v6/summary/tables.md).
- [Reviewed dataset description](/home/saranshlulla/Documents/Capstone/ecopath/research/data_collection/soib2023-v1/reviewed-v4/README.md).
- [Frozen held-out protocol](/home/saranshlulla/Documents/Capstone/ecopath/research/artifacts/final-qwen-a09a354-v1/protocol.json) and saved output log, inspected read-only.

