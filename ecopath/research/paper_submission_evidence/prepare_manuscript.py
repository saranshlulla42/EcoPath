"""Prepare an IEEE manuscript copy and private supplementary evidence."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil

ROOT=Path(__file__).resolve().parents[2]
SRC=Path('/home/saranshlulla/Downloads')
OUT=ROOT/'output/EcoPath_IEEE_Review'
SUP=OUT/'supplement'
FIG=OUT/'figures'


def between(text, start, end, replacement):
    if text.count(start)!=1:
        raise ValueError(f'Expected unique start anchor: {start!r}')
    before,tail=text.split(start,1)
    if end not in tail:
        raise ValueError(f'End anchor not found after {start!r}: {end!r}')
    _,after=tail.split(end,1)
    return before+start+'\n'+replacement+'\n\n'+end+after


def exact(text, old, new):
    if text.count(old)!=1:
        raise ValueError(f'Expected one occurrence of {old[:100]!r}: found {text.count(old)}')
    return text.replace(old,new,1)


def main():
    for folder in (OUT,SUP,FIG): folder.mkdir(parents=True,exist_ok=True)
    for name in ('figure1_architecture.pdf','figure2_pipeline.pdf'):
        shutil.copy2(SRC/name,FIG/name)
    text=(SRC/'main.tex').read_text(encoding='utf-8')
    text=between(text,r'\begin{abstract}',r'\end{abstract}',r'''Conservation report drafting from incomplete biodiversity records requires explicit separation of supplied facts from unknowns. We study parameter-efficient adaptation of Qwen2.5-7B-Instruct for evidence-bounded drafting in EcoPath. An archived 15-species pilot found valid JSON in 15/15 adapted and 0/15 unadapted responses, under a prompt that did not explicitly require JSON. A separate matched study compares a newly trained QLoRA adapter with the unadapted model under identical engineered prompts and schema enforcement on 60 held-out species with three evidence variants (180 reports per condition). Under the prespecified punctuation-sensitive structured-field check, success was 1620/1620 for QLoRA and 1168/1620 for the unadapted model, a paired difference of 27.9 percentage points (95\% species-bootstrap interval: 27.2--29.0). A post-hoc analysis found that 435 of 443 assessable baseline value mismatches differed only by a terminal period. Ignoring terminal periods reduced the paired difference to 1.0 percentage point (95\% interval: 0.0--2.5). These are automated agreement measures for one evaluated seed and source format; they do not establish ecological correctness or conservation-decision validity.''')

    text=between(text,r'\subsection{Primary Dataset and Partitions}',r'\begin{table}[t]',r'''We constructed an India-framed dataset of 120 species using a fixed \emph{State of India's Birds 2023} snapshot \cite{soib}. The source table contained 1,357 records, of which 942 were marked selected for SoIB; 44 exact scientific names in the historical dataset were excluded, leaving 898 candidates. A seed-42 round robin across current annual-trend categories selected 30 development species with distinct genera. From the remaining eligible names and genera, a second seed-9173 stratified round robin selected 90 species; the first 30 formed validation and the next 60 test. The resulting partitions have no shared genera and do not constitute a probability sample. Exact-name exclusion does not resolve all synonyms. Three names were updated using a later taxonomy crosswalk while stable source IDs remained anchored to the 2023 table. Source extraction was AI-assisted and checked against identified rows of the checksum-verified source, not independently validated by ornithologists.

For each species, \emph{complete}, \emph{partial}, and \emph{minimal} variants exposed six, three, and zero of the six collected fields, respectively. ``Complete'' refers to collected fields, not complete ecological evidence. For each species, seed 9173 and its stable species ID deterministically shuffled the six available fields; the partial variant masked three, and the minimal variant masked all six. A dependency check also masked direct echoes of hidden values; no additional dependency masks occurred in this dataset. Population size, breeding and species-specific threats remained absent in every variant. The resulting development and validation partitions each contained 90 examples, and the test partition contained 180 inputs per model. The split manifest and per-variant field masks are provided in the local supplement.''')

    text=between(text,r'\subsection{Prompt and Output Contract}',r'\subsection{Model Training and Matched Comparison}',r'''Both arms used the same instruction to use supplied evidence only, return schema-conforming JSON, cite the supplied identifiers, and represent missing fields as null. The saved messages consist of a system message containing the complete JSON Schema, one validation user/assistant demonstration (\texttt{soib2023:Oenanthe\_fusca:partial}), and the test user message. The input serializes source values and synthetic canonical excerpts; original source-row excerpts and provenance remain in the local source ledger. A comparison of all 180 paired examples found identical message text, prompt token IDs, payload hashes, generation settings, and requested LM Format Enforcer constraints. The full verbatim messages, schema, native chat template, tokenizer IDs and example evidence are in the accompanying local supplement.''')

    old=r'''Each arm attempted all 180 test variants in a separate process on an 8 GiB RTX 3070 Laptop GPU. Thus the contrast isolates the tested adapter under the shared inference contract rather than comparing adaptation against a deliberately weak prompt.'''
    new=r'''Each arm attempted all 180 test variants in a separate process on an 8 GiB RTX 3070 Laptop GPU. The seed-42 adapter selected checkpoint 36 by minimum validation loss ($2.5038\times10^{-5}$); measured training time including validation and checkpoints was 1,304.9 s. The contrast isolates the tested adapter under the shared inference contract rather than comparing adaptation against a deliberately weak prompt.'''
    text=exact(text,old,new)

    old=r'''where $V_r$ denotes schema validity, $M_{rj}$ correct value or null, and $C_{rj}$ the required source association (vacuously true for an absent value). Thus the primary rate is $\sum_{r,j}I_{rj}/1620$. We separately calculate (i) available-value agreement over 540 non-null targets, (ii) correct abstention over 1080 absent targets, (iii) structural validity and full-schema compliance, and (iv) source-associated agreement among assessable fields.'''
    new=r'''where $V_r$ denotes an assessable schema-valid, non-truncated output, $M_{rj}$ agreement with the expected value or null, and $C_{rj}$ the required source association (vacuously true for an absent value). Thus the primary rate is $\sum_{r,j}I_{rj}/1620$. String matching normalizes case and whitespace and maps explicit IUCN aliases, but preserves terminal punctuation; lists are compared without order. We separately report available-value agreement over 540 non-null targets, correct abstention over 1080 absent targets, schema compliance and source-associated agreement among assessable fields. A separately labeled post-hoc sensitivity analysis also removes terminal periods before applying the same comparison; it is not a semantic entailment test.'''
    text=exact(text,old,new)

    start=r'\subsection{Primary Matched Evaluation}'
    end=r'\begin{table}[t]'
    pos=text.index(start);before=text[:pos];tail=text[pos:]
    tail=between(tail,start,end,r'''Table~\ref{tab:main} reports the frozen strict check. Both conditions were almost always parseable under the shared schema constraint. The evaluated adapter matched 540/540 available targets and the unadapted model matched 94/540 under the punctuation-sensitive comparison. Correct null handling was already high in the unadapted condition (1074/1080). The numerical gap principally reflects exact serialization: 435 of 443 assessable baseline value mismatches differed only in a final period, and the other eight were shortened labels lacking the longer source-context phrase. These differences must not be interpreted as 443 demonstrated ecological errors.''')
    text=before+tail
    text=exact(text,r'\caption{Matched test results: 60 held-out species, 180 reports/arm.}',r'\caption{Matched test results under the original punctuation-sensitive check: 60 species, 180 reports/arm.}')
    text=exact(text,r'''Source association is checked against reviewed structured assertions, not independent ecological truth. A failed schema makes its fields unsuccessful.''',r'''Strict matching preserves terminal periods. Source association is checked against reviewed structured assertions, not independent ecological truth. Structurally invalid or truncated reports count as failures.''')
    old=r'''The end-to-end field success rates were 72.1\% (1168/1620) for the base and 100.0\% (1620/1620) for the evaluated adapter. The observed paired difference was 27.9 percentage points (95\% species bootstrap: 27.2--29.0). The narrow interval is conditional on this dataset, prompt, source representation, selected seed, and evaluation protocol; it should not be generalized to other datasets or training runs without replication. One unadapted report reached the generation cap, and there were no recorded execution errors.'''
    new=r'''The original end-to-end rates were 72.1\% (1168/1620) and 100.0\% (1620/1620), a paired difference of 27.9 percentage points (95\% species bootstrap: 27.2--29.0). In the post-hoc terminal-period-insensitive analysis, the corresponding counts were 1603/1620 and 1620/1620, a difference of 1.0 percentage point (95\% interval: 0.0--2.5); available-value agreement became 529/540 and 540/540. This sensitivity analysis was chosen after inspecting outputs and does not assess semantic equivalence. One unadapted report reached the generation cap, with no recorded execution errors.'''
    text=exact(text,old,new)
    old=r'''Performance differed by evidence variant (Table~\ref{tab:variants}). The unadapted model achieved 44.4\% on complete inputs, 71.9\% on partial inputs, and 100\% on minimal inputs. The minimal case required nulls for every field; it is consequently the least informative test of extracting supported values. With more evidence present, successful generation demanded accurate source-value reproduction, which was the main failure mode of the unadapted comparator. The evaluated adapter passed all structured-field checks in each variant, subject to the stated test limitations.'''
    new=r'''Under the punctuation-sensitive check, performance differed by evidence variant (Table~\ref{tab:variants}). The minimal case required nulls for every field and is therefore the least informative test of copying supplied values. The apparent baseline deficit with more evidence largely reflects terminal punctuation rather than demonstrated ecological errors. The evaluated adapter matched all structured-field checks in this sample, subject to the stated test limitations.'''
    text=exact(text,old,new)
    text=exact(text,r'\caption{Field success by evidence variant (540 fields per arm and variant).}',r'\caption{Punctuation-sensitive field success by evidence variant (540 fields per arm and variant).}')
    old=r'''A reported $0/537$ false-abstention count for the base arm means that assessable expected non-null fields were not incorrectly replaced by null; it does \emph{not} mean that those fields contained correct values. Indeed, most assessable non-null predictions did not match the expected structured assertions. The 537 assessable-field denominator differs from the 540 intended non-null targets because structural output failures are retained in end-to-end metrics.'''
    new=r'''The base arm's $0/537$ false-abstention count concerns only assessable fields expected to be non-null; it does not establish that those values matched exactly. The denominator is 537 rather than 540 because one partial-evidence output, \textit{Neophron percnopterus}, reached 768 output tokens and failed JSON parsing, excluding its three available fields from assessable-only rates. Its three available and six missing fields remain failures in end-to-end metrics. The matched adapted output was assessable.'''
    text=exact(text,old,new)

    point=r'\subsection{Historical Pilot and Illustrative Behavior}'
    insert=r'''\begin{table}[t]
\centering
\caption{A saved complete-evidence example illustrates a strict punctuation mismatch; both models cite the same source ID.}
\label{tab:example}
\footnotesize
\begin{tabularx}{\columnwidth}{@{}lX@{}}
\toprule
\textbf{Item} & \textbf{Saved value} \\
\midrule
Species / field & \textit{Hemipus picatus}, diet \\
Source excerpt & \texttt{Diet Guild=Invertebrate} (SoIB record 654) \\
Expected / QLoRA & \texttt{SoIB 2023 diet-guild classification: Invertebrate.} \\
Unadapted & \texttt{SoIB 2023 diet-guild classification: Invertebrate} \\
Source ID & \texttt{s-462f42e71095a56a34f3} \\
\bottomrule
\end{tabularx}
\end{table}

The example in Table~\ref{tab:example} is counted as a strict mismatch solely because the base output omits the last period. Another saved output for \textit{Acridotheres grandis} returned the diet value \texttt{Invertebrate} with the correct source ID but without the expected longer classification phrase; the adapted output retained that phrase. These are observed formatting/content differences, not independently adjudicated ecological errors. The local supplement contains full example inputs and outputs, including the truncated report.

'''
    text=exact(text,point,insert+point)
    old=r'''The matched design substantially strengthens the inference relative to the pilot: both conditions faced identical engineered prompts and schema enforcement. Thus a near-perfect baseline JSON rate (179/180) demonstrates that format generation largely can be handled through prompting and constrained decoding. The adaptation-associated improvement was instead concentrated in field/source agreement for the specific supervised reporting contract. This is a useful integration result: a reviewer-facing system can display available evidence and visibly preserve unknowns without silently filling gaps.'''
    new=r'''The matched design holds engineered prompts and schema enforcement constant. The baseline's 179/180 valid JSON outputs show that this format can largely be achieved without adaptation in the tested setting. The large strict-copying gap is predominantly attributable to omitted terminal periods; the smaller post-hoc punctuation-insensitive gap has an interval including zero. This study therefore does not establish a comparable gain in ecological fidelity. Both training targets and test inputs share a templated source representation, which favors assessment of structured copying rather than open-ended ecological reasoning.'''
    text=exact(text,old,new)
    old=r'''The single-GPU, batch-one mean wall times were 25.5\,s/report for the base condition and 29.4\,s/report for the adapter. They exclude loading and warm-up and are not deployment throughput estimates.'''
    new=r'''The single-GPU, batch-one mean wall times were 25.5\,s/report for the base condition and 29.4\,s/report for the adapter. They exclude model loading and one warm-up generation per arm and are not deployment throughput estimates. Seed-42 training used 1,304.9\,s including validation and checkpointing, excluding model loading and preprocessing.'''
    text=exact(text,old,new)

    text=between(text,r'\section{Reproducibility and Ethical Use}',r'\section{Conclusion}',r'''The fixed 2023 State of India's Birds source \cite{soib}, source IDs, URLs, original row excerpts, retrieval dates, rights metadata, protocol, data hashes, adapter metadata, outputs and metric scripts are retained locally. The accompanying private supplement contains the exact matched messages and schema, split and mask manifests, paired outputs, metric audit, post-hoc sensitivity analysis and a reproduction guide. No public repository is claimed; reuse and redistribution terms for the newer taxonomy cross-check remain unresolved. The canonical JSON body of the frozen protocol, excluding its hash field, has SHA-256 \texttt{b0fc3242e40019a5\allowbreak 5578a50c2d10f866\allowbreak 3d4e5f0eab32a9bd\allowbreak c448270aea9e7d79}. This is distinct from the protocol file's byte-level SHA-256. The original seven-method, three-seed plan was reduced before these two matched test arms were generated; only seed 42 is evaluated here.

AI assistance was used in source-extraction review and manuscript preparation, and the archived pilot used teacher-generated targets and LLM-based historical ratings. Venue-specific disclosure requirements have not yet been selected. The system was not validated for autonomous conservation recommendations.''')
    text=between(text,r'\section{Conclusion}',r'\section*{Acknowledgment}',r'''For evidence-bounded bird-report drafting in EcoPath, the seed-42 QLoRA adapter and a strongly prompted unadapted model were compared on 60 held-out species under identical schema constraints. The prespecified punctuation-sensitive check favored QLoRA by 27.9 percentage points, but 435 baseline mismatches differed only by a final period. A post-hoc punctuation-insensitive check reduced the paired difference to 1.0 percentage point, with a 95\% species-bootstrap interval of 0.0--2.5. These findings demonstrate sensitivity to output normalization and do not establish an ecological-fidelity advantage, cross-seed robustness, or practical conservation benefit. The historical pilot does not establish that fine-tuning is necessary for JSON generation.''')
    text=exact(text,r'''The authors acknowledge guidance from the Department of Computer Engineering, Vivekanand Education Society's Institute of Technology. The study's contributors and disclosure text should be verified against the final authorship agreement before submission.''',r'''The authors acknowledge guidance from the Department of Computer Engineering, Vivekanand Education Society's Institute of Technology.''')

    text=re.sub(r'\\paperTODO\{[^{}]*\}','',text)
    text=exact(text,r'\newcommand{\paperTODO}[1]{\par\noindent\textcolor{red}{\textbf{[TODO for final submission:} #1\textbf{]}}\par}'+'\n','')
    if '\\paperTODO' in text or '[TODO for final submission:' in text:
        raise ValueError('Unresolved manuscript TODO markers')
    (OUT/'main.tex').write_text(text,encoding='utf-8')

    export=ROOT/'research/paper_submission_evidence'
    for name in ('exact_messages_example.json','exact_json_schema.json','exact_prompt_token_ids.json','exact_chat_template.jinja',
                 'species_split_manifest.csv','variant_field_masks.csv','illustrative_examples.json',
                 'baseline_mismatched_fields.json','audit_summary.json','sensitivity_analysis.json','build_evidence.py'):
        shutil.copy2(export/name,SUP/name)
    data=ROOT/'research/data_collection/soib2023-v1/reviewed-v4'
    shutil.copy2(data/'all_variants.PRIVATE.jsonl',SUP/'all_variants.PRIVATE.jsonl')
    shutil.copy2(data/'source_review_ledger.jsonl',SUP/'source_review_ledger.jsonl')
    shutil.copy2(data/'taxonomy_crosswalk.jsonl',SUP/'taxonomy_crosswalk.jsonl')
    frozen=ROOT/'research/artifacts/final-qwen-a09a354-v1'
    shutil.copy2(frozen/'protocol.json',SUP/'frozen_protocol.json')
    run=frozen/'run.jsonl'
    with run.open(encoding='utf-8') as source, (SUP/'matched_outputs.jsonl').open('w',encoding='utf-8') as out:
        for line in source:
            row=json.loads(line)
            if row['method_id'] in ('constrained','qlora-42'): out.write(line)
    for name in ('summary.json','paired-field-success.json','metrics.csv'):
        shutil.copy2(frozen/'reduced-summary'/name,SUP/('matched_'+name))
    adapter=ROOT/'research/artifacts/training.qwen-a09a354-v4/seed-42/selected_adapter'
    for name in ('adapter_config.json','adapter_provenance.json'):
        shutil.copy2(adapter/name,SUP/name)
    shutil.copy2(ROOT/'research/artifacts/training.qwen-a09a354-v4/seed-42/training_result.json',SUP/'seed42_training_result.json')
    code=SUP/'frozen_code';(code/'research').mkdir(parents=True,exist_ok=True);(code/'backend').mkdir(exist_ok=True)
    for path in (ROOT/'research').glob('*.py'):shutil.copy2(path,code/'research'/path.name)
    for name in ('evidence_contract.py','evidence_prompts.py','__init__.py'):
        path=ROOT/'backend'/name
        if path.exists():shutil.copy2(path,code/'backend'/name)
    shutil.copy2(ROOT/'research/docs/DEADLINE_EVALUATION_AMENDMENT.md',SUP/'DEADLINE_EVALUATION_AMENDMENT.md')
    print(f'Prepared {OUT}')


if __name__=='__main__':main()
