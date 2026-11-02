"""Preserve original PDF pages and replace only audited text blocks.

Run with the bundled document Python after both matched evaluation arms finish.
No PDF is written until the complete frozen comparison has been checked.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, ContentStream, TextStringObject
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path('/home/saranshlulla/Downloads/Paper 2nd draft.pdf')
if not SOURCE.exists():
    SOURCE = ROOT / 'research/paper_revision/Paper 2nd draft.pdf'
RUN_DIR = ROOT / 'research/artifacts/final-qwen-a09a354-v1'
EVIDENCE = RUN_DIR / 'reduced-summary/paper-evidence.json'
OUTPUT = ROOT / 'output/pdf/EcoPath_Paper_Minimal_Revision.pdf'
WIDTH = 447.2126


def compose(c, m):
    a, b, cc, d, e, f = c
    A, B, C, D, E, F = m
    return (a*A+cc*B, b*A+d*B, a*C+cc*D, b*C+d*D, a*E+cc*F+e, b*E+d*F+f)


def text_groups(page, pdf):
    stream = ContentStream(page.get_contents(), pdf)
    ctm = (1., 0., 0., 1., 0., 0.)
    stack = []
    groups = []
    group = None
    font = None
    size = None
    leading = None
    for index, (values, op) in enumerate(stream.operations):
        if op == b'q':
            stack.append(ctm)
        elif op == b'Q':
            ctm = stack.pop()
        elif op == b'cm':
            ctm = compose(ctm, tuple(map(float, values)))
        elif op == b'BT':
            group = dict(begin=index, ctm=ctm, text='', font=font, size=size,
                         leading=leading, newlines=0, moves=[])
        elif op == b'Tf':
            font, size = str(values[0]), float(values[1])
            group.update(font=font, size=size)
        elif op == b'TL':
            leading = float(values[0])
            group['leading'] = leading
        elif op in (b'Tm', b'Td'):
            group['moves'].append((op.decode(), list(map(float, values))))
        elif op == b'Tj':
            group['text'] += str(values[0])
        elif op == b'TJ':
            group['text'] += ''.join(str(x) for x in values[0] if isinstance(x, str))
        elif op == b'T*':
            group['text'] += '\n'
            group['newlines'] += 1
        elif op == b'ET':
            if group['text'].strip():
                group.update(end=index, id=len(groups))
                groups.append(group)
            group = None
    return stream, groups


def pct(value):
    return 'undefined' if value is None else f'{100*value:.1f}%'


def fraction(metric):
    return f"{metric['numerator']}/{metric['denominator']} ({pct(metric['value'])})"


def summary_map(evidence):
    return {(r['method_id'], r['level']): r for r in evidence['summaries']}


def prose_results(evidence, summaries):
    primary = evidence['primary']
    a = summaries[('constrained', 'all')]['metrics']['micro']
    b = summaries[('qlora-42', 'all')]['metrics']['micro']
    effect = 100*primary['estimate']
    low, high = (100*x for x in primary['ci95'])
    estimate = (f"End-to-end field success was {pct(b['structured_field_success_e2e']['value'])} "
                f"for QLoRA and {pct(a['structured_field_success_e2e']['value'])} for the unadapted comparator "
                f"(paired difference {effect:+.1f} percentage points; 95% species bootstrap interval {low:+.1f} to {high:+.1f}).")
    available_a = a['available_reporting_e2e']['value']
    available_b = b['available_reporting_e2e']['value']
    if primary['estimate'] > 0 and available_b < available_a:
        interpretation = ('Field-success point estimates favoured the adapter, but available-value agreement was lower; '
                          'the result is mixed and does not establish overall evidence-use advantage.')
    elif primary['estimate'] > 0 and primary['ci95'][0] > 0:
        interpretation = ('The evaluated adapter improved automatic field success under these conditions; '
                          'this does not establish ecological truth, reviewer benefit, or seed invariance.')
    elif primary['estimate'] > 0:
        interpretation = ('The field-success point estimate favoured the adapter, but its bootstrap interval spanned zero; '
                          'incremental advantage remains unconfirmed under these conditions.')
    elif primary['estimate'] < 0:
        interpretation = ('Field-success point estimates favoured the unadapted model; '
                          'the adapter demonstrated no incremental advantage on this measure.')
    else:
        interpretation = ('Field-success estimates were equal; the adapter demonstrated '
                          'no incremental advantage on this measure.')
    return a, b, estimate, interpretation


def replacement_blocks(evidence, summaries):
    a, b, estimate, interpretation = prose_results(evidence, summaries)
    abstract = (
        'Preparing a conservation report from incomplete biodiversity information requires more than a fluent summary: '
        'the report must preserve the distinction between available evidence and unanswered questions. '
        'We investigated whether parameter-efficient fine-tuning could help a language model perform this task within '
        'EcoPath, a geospatial bird-intelligence platform. An archived QLoRA experiment adapted Qwen2.5-7B-Instruct '
        'on 85 synthetic examples with taxonomy-only inputs. On 15 held-out species, valid JSON and required-key '
        'presence were observed in 15/15 adapted responses and 0/15 base responses; the original prompt did not '
        'explicitly require JSON. We then compared a newly trained adapter with a strongly prompted unadapted model '
        'on 60 additional held-out species under three evidence variants, using identical prompts and schema constraints. '
        + estimate + ' Available-value agreement, abstention and source associations were assessed separately. '
        'This single-seed comparison evaluates agreement with reviewed structured assertions, rather than independent '
        'ecological correctness. EcoPath retains a bounded report-drafting role while the measured results qualify '
        'the incremental contribution of adaptation.'
    )
    # Indices refer to the supplied, unchanged PDF's text objects. The script
    # independently recovers them on each run and records every replacement.
    edits = {
        (1, 6): abstract,
        (2, 4): (
            'The study addressed two questions: (i) how does QLoRA adaptation change structural compliance on '
            'held-out species under the same reporting prompts, and (ii) what differences in missing-information '
            'handling are apparent in automated ratings and illustrative outputs? We expected the adapted model '
            'to follow the report schema more consistently. We treated the second question as exploratory because '
            'the original inputs did not vary the principal ecological fields. A subsequent matched comparison on '
            '60 held-out species (Appendix B) tested supplied-evidence use under identical prompting and schema constraints.'
        ),
        (3, 8): (
            'We implemented the drafting task within EcoPath and evaluated the same instruction-tuned model with '
            'and without a QLoRA adapter. Sections 3-5 describe the archived synthetic-data experiment and its '
            '15-species comparison. Appendix B reports a separate sourced dataset, new training and a matched '
            '60-species evaluation addressing the same drafting purpose.'
        ),
        (5, 2): (
            'The workflow consisted of preparing species-linked targets, dividing the dataset into training and held-out '
            'subsets, adapting the model, and generating paired reports (Figure 2). Each model condition received the '
            'same held-out species payload and reporting prompt. We assessed parseability and required-key presence, '
            'then obtained supplementary automated ratings. The archived prompt did not explicitly require JSON or '
            'supply a schema; Appendix B adds a matched, explicitly constrained comparison.'
        ),
        (5, 15): (
            'Target reports identified many evidence gaps, exposing the model to a consistent structured drafting '
            'pattern. However, the synthetic targets were not independently verified conservation references: '
            'source auditing also identified heuristic risk language unsupported by the taxonomy-only inputs. '
            'Because the principal ecological fields were absent throughout, this dataset could not test whether '
            'the model would selectively report supported values when richer evidence became available.'
        ),
        (5, 16): (
            'Using a deterministic split with seed 42, we assigned 85 species examples to training and 15 to held-out '
            'evaluation. There was no separate validation partition or recorded validation-based checkpoint '
            'selection. Species were disjoint, but Larus and Turdus occurred in both splits. The evaluation species '
            'are listed in Appendix A. Although EcoPath has an India-focused motivation, this geographically broader '
            'held-out list was not designed to estimate performance specifically on Indian birds.'
        ),
        (6, 29): (
            'We assessed JSON validity after removing optional Markdown fences, then checked the presence of '
            'six component keys: species, current conservation status, key threats, survivability assessment, '
            'mitigation actions, and sources. The historical check accepted flat or nested layouts and did not '
            'validate field types or a full JSON schema. These measures describe parseability and key presence; '
            'they do not verify factual support. Full schema validation is used in Appendix B.'
        ),
        (6, 30): (
            'A Gemini-family LLM judge assigned five-point ratings for format, grounding, completeness and '
            'usefulness to all 30 responses. Its context was limited to the first 600 characters of the user prompt, '
            'generally omitting the source-result section. These historical ratings therefore do not establish '
            'fidelity to the full supplied evidence. No blinded human validation or teacher-judge independence was established.'
        ),
        (7, 6): (
            'All 15 adapted responses were valid JSON and contained the required keys, compared with none of the '
            'unadapted responses (Table 3). The base model returned Markdown prose under an instruction requesting '
            'a structured report, without explicitly requiring JSON. Parse failure and required-key failure therefore '
            'coincided. This weak baseline does not establish that adaptation is necessary for JSON output.'
        ),
        (7, 16): 'Required-key presence',
        (8, 1): (
            '<b>Figure 3.</b> Historical automated ratings. Judge identity is unverified; context was limited to 600 '
            'prompt characters, generally omitting source excerpts. Scores do not validate full-evidence fidelity.'
        ),
        (8, 6): (
            'The archived comparison shows that a small synthetic training set could establish a learned JSON '
            'reporting pattern under the tested instruction. A structured response can be parsed and presented '
            'through a consistent interface. However, the instruction did not explicitly require JSON, so the result '
            'does not establish superiority over strong prompting. The matched comparison in Appendix B evaluates '
            'the adapter under the same explicit prompt and output constraints as its unadapted comparator.'
        ),
        (8, 7): (
            'The supplementary ratings favoured the adapted reports, but their interpretation is limited by the '
            'judge context: only a 600-character prompt prefix was supplied, generally excluding source excerpts. '
            'These scores cannot show that the judge checked each report against the complete supplied evidence. '
            'Structure, brevity and similarity to the target style may also have influenced the ratings. We retain '
            'them as historical descriptive observations and use the direct structured-source checks in Appendix B '
            'to examine evidence agreement without treating automated judging as ecological validation.'
        ),
        (9, 5): (
            'Our findings fit the task-specific adaptation enabled by LoRA and QLoRA [4,6]. The contribution here '
            'is an application in which report structure and missing-information statements can be learned from a '
            'small dataset. Castro et al. [9] demonstrate the promise of prompt-based ecological processing, '
            'motivating a strong prompting comparator. Appendix B supplies this control while keeping the '
            'evidence and schema constraints identical between the unadapted and adapted conditions.'
        ),
        (9, 7): (
            'Tam et al. [10] motivate distinguishing format adherence from task success, while Zheng et al. [8] '
            'explain why automated judgements require scrutiny. The follow-up evaluation in Appendix B holds '
            'the output contract constant and compares the adapted model with a strongly prompted unadapted '
            'model on available and missing evidence. Its structured-source agreement measures address the '
            'original experiment\'s evidence-use gap, while remaining distinct from ecological or practical validation.'
        ),
        (10, 4): (
            'The archived comparison included one weak prompting condition, one training run and no independent '
            'validation set. Its incomplete runtime and hardware record limits reproducibility and cost analysis. '
            'Appendix B adds a pinned model revision, validation-based checkpoint selection and a matched '
            'constrained baseline. Only seed 42 was evaluated there; although three adapters were trained, '
            'the deadline-reduced comparison cannot estimate variation across training seeds.'
        ),
        (10, 3): (
            'The original evidence design limited the interpretation of missing-information handling: verified '
            'status, trend, population, habitat and range values were absent, so selective abstention could not '
            'be distinguished from a repeated unavailable-field response. Appendix B varies availability for '
            'six collected fields and measures supplied-value agreement and abstention jointly; wider ecological validity remains untested.'
        ),
        (10, 5): (
            'Historical judge scores were not validated against blinded human review. The 600-character context '
            'limit, unverified judge identifier and unresolved teacher-judge independence prevent interpreting '
            'the rubric as calibrated ecological correctness. The newer checks compare output values and citations '
            'with reviewed structured assertions; source review was AI-assisted, not independent ornithologist '
            'validation. Neither experiment establishes reviewer benefit or formal conservation-assessment accuracy.'
        ),
        (10, 7): (
            'We studied QLoRA adaptation for structured bird report drafting in EcoPath. '
            'Archived 15-species adapted outputs produced valid JSON and required keys, whereas the base model returned prose. '
            'A matched 60-species comparison under identical prompts and schema constraints evaluated evidence fidelity '
            '(Appendix B). ' + interpretation
        ),
        (10, 8): (
            'Learning a reporting pattern and using supplied evidence remain separate outcomes. The follow-up '
            'comparison measures available-value agreement, abstention and structural failures directly, '
            'while its single evaluated seed and dated, selected dataset limit generalisation. Further '
            'training-seed replication and independent ecological assessment remain outside the measured scope.'
        ),
        (11, 12): 'A Archived Held-Out Evaluation Materials',
        (12, 3): 'Base: JSON / keys',
        (12, 4): 'Adapted: JSON / keys',
        (12, 60): (
            'Cases were not randomly selected. Their historical judge scores use truncated prompt context and do not '
            'measure complete-evidence fidelity; these examples do not estimate factual error frequency.'
        ),
    }
    return edits


def style(name, font='Times-Roman', size=10.5, leading=13.6, **kw):
    return ParagraphStyle(name, fontName=font, fontSize=size, leading=leading,
                          textColor=colors.black, **kw)


def make_appendix(evidence, summaries):
    a, b, estimate, interpretation = prose_results(evidence, summaries)
    mem = BytesIO()
    doc = SimpleDocTemplate(mem, pagesize=A4, leftMargin=24*mm, rightMargin=24*mm,
                            topMargin=21*mm, bottomMargin=20*mm)
    body = style('body', alignment=TA_JUSTIFY, spaceAfter=7)
    heading = style('heading', 'Times-Bold', 13, 16, spaceAfter=9)
    subheading = style('subheading', 'Times-Bold', 11.4, 14.5, spaceBefore=7, spaceAfter=7)
    caption = style('caption', size=9.2, leading=11.4, spaceBefore=4, spaceAfter=6)
    cell = style('cell', size=9, leading=11.2)
    header = style('header', 'Times-Bold', 9, 11.2)
    small = style('small', size=9.1, leading=11.5, spaceAfter=5)
    flow = []
    def p(text):
        flow.append(Paragraph(text, body))
    def table(headers, rows, widths):
        cells = [[Paragraph(escape(str(s)), header) for s in headers]]
        cells += [[Paragraph(escape(str(s)), cell) for s in row] for row in rows]
        t = Table(cells, colWidths=widths, hAlign='LEFT', repeatRows=1)
        t.setStyle(TableStyle([
            ('LINEABOVE', (0,0), (-1,0), 0.8, colors.black),
            ('LINEBELOW', (0,0), (-1,0), 0.45, colors.black),
            ('LINEBELOW', (0,-1), (-1,-1), 0.8, colors.black),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 4),
            ('RIGHTPADDING', (0,0), (-1,-1), 4),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ]))
        flow.append(t)
        flow.append(Spacer(1, 7))

    flow.append(Paragraph('B Matched Held-Out QLoRA Evaluation', heading))
    flow.append(Paragraph('B.1 Dataset and matched conditions', subheading))
    p('To address the same report-drafting purpose with informative ecological inputs, we curated a separate '
      '120-species India-frame dataset from State of India\'s Birds 2023. Development, validation and test '
      'partitions contained 30, 30 and 60 species, respectively, with no shared genera. Six fields could be '
      'supplied: recorded IUCN category, India-specific population trend, habitat, range-size category, diet '
      'and migration. Population size, breeding and species-specific threats remained null. Complete, partial '
      'and minimal variants exposed six, three and zero of the six supported fields; "complete" therefore '
      'means complete for the collected evidence, not a comprehensive conservation assessment.')
    p('The new adapter used 90 development examples (30 species x three variants) and 90 validation examples. '
      'Targets copied supplied values and source IDs, using null otherwise. '
      'QLoRA used rank 16, alpha 32, dropout 0.05, the seven projection targets in Section 3.4, learning '
      'rate 2 x 10<super>-4</super>, batch one, accumulation eight and three epochs (36 optimizer steps). '
      'Training used the native chat template, assistant-only loss, a compact schema representation and '
      'no sequence truncation. Epoch checkpoints were selected by validation loss. Three seeds were trained; '
      'seed 42, fixed as the first planned seed before either matched test arm was generated, alone was '
      'evaluated for this submission.')
    p('Both conditions used Qwen2.5-7B-Instruct revision a09a35458c702b33eeacc393d103063234e8bc28, '
      'a 4-bit NF4 backbone with double quantization and fp16 computation, identical full engineered prompts '
      'and one validation demonstration, and the same LM Format Enforcer schema constraint. Greedy decoding '
      'used a 4,096-token input budget and 768 new tokens, with no evidence truncation. Each condition '
      'attempted all 180 held-out variants in its own process on an 8 GiB RTX 3070 Laptop GPU.')
    flow.append(Paragraph('B.2 Paired results', subheading))
    p(estimate)
    flow.append(Paragraph('<b>Table 6.</b> Matched test results (60 species, 180 outputs per condition). '
                          'Counts retain structural failures. Agreement refers to reviewed structured assertions.', caption))
    metrics = [
        ('Valid JSON', 'json_validity'),
        ('Full-schema compliance', 'schema_compliance'),
        ('Field success, end to end', 'structured_field_success_e2e'),
        ('Available-value agreement, end to end', 'available_reporting_e2e'),
        ('Correct abstention, end to end', 'correct_abstention_e2e'),
        ('False abstention, assessable fields', 'false_abstention_assessable'),
        ('Cited structured-source agreement', 'citation_structured_support'),
    ]
    rows = [(label, fraction(a[key]), fraction(b[key])) for label, key in metrics]
    for label, key in [('Generation-cap hits', 'truncated'), ('Execution errors', 'errors')]:
        rows.append((label, str(evidence['execution']['constrained'][key]),
                     str(evidence['execution']['qlora-42'][key])))
    table(['Metric', 'Unadapted', 'QLoRA seed 42'], rows, [199.2, 124, 124])

    flow.append(PageBreak())
    flow.append(Paragraph('B.3 Evidence availability and interpretation', subheading))
    flow.append(Paragraph('<b>Table 7.</b> End-to-end field success by evidence variant; '
                          'each variant includes all 60 test species and 540 fields per condition.', caption))
    rows = []
    for level in ('complete', 'partial', 'minimal'):
        aa = summaries[('constrained', level)]['metrics']['micro']['structured_field_success_e2e']
        bb = summaries[('qlora-42', level)]['metrics']['micro']['structured_field_success_e2e']
        rows.append((level.capitalize(), fraction(aa), fraction(bb)))
    table(['Evidence variant', 'Unadapted', 'QLoRA seed 42'], rows, [199.2, 124, 124])
    p(interpretation)
    p('A successful field contains the supplied value with the expected source association, or the required '
      'null when evidence is absent. Structural failures count as failures for all fields. Minimal variants '
      'have no available facts, so success there measures null handling rather than supported extraction. '
      'We therefore report available-value agreement alongside the aggregate score. Citation identifiers '
      'can be valid even when an output value differs from the corresponding source assertion; automated '
      'matching is not a semantic assessment of unrestricted prose or independent ecological truth.')
    pa = summaries[('constrained', 'all')]['mean_wall_seconds']
    pb = summaries[('qlora-42', 'all')]['mean_wall_seconds']
    p(f'Mean per-example wall time was {pa:.1f} seconds for the unadapted condition and {pb:.1f} seconds '
      'for QLoRA. These single-GPU, batch-one measurements exclude model loading and warmup and do not '
      'establish deployment throughput or amortized training cost. The paired effect averages the three '
      'variants within species and then across species. Its percentile interval uses 2,000 paired species '
      'bootstrap draws with seed 42, retaining variants together; it does not estimate training-seed variation.')
    flow.append(Paragraph('B.4 Scope, provenance and reproducibility', subheading))
    p('The original seven-method, three-seed test plan was reduced for the submission deadline before '
      'generating these two prioritized arms. Other methods and seeds were deferred, and partial original-prompt '
      'outputs were preserved but excluded from this paired analysis. The original frozen protocol and its '
      'generation settings were retained. This amendment is disclosed; the submission is not presented as '
      'a completed seven-method comparison. The archived 15-species experiment uses a different dataset, '
      'adapter and report contract and is not pooled with these results.')
    p('The selected sampling frame is not a probability sample. All source values are from the fixed 2023 '
      'snapshot and are not claims about current conservation categories. Source IDs, URLs, retrieval dates, '
      'excerpts and rights metadata are retained; unavailable fields remain null. Source extraction review '
      'was AI-assisted, without independent ornithologist validation. The study does not measure conservation '
      'decision quality, reviewer usefulness or field-assessment accuracy. Synthetic targets, historical '
      'automated judging and AI assistance in source auditing and manuscript preparation are disclosed.')
    flow.append(Paragraph('Source: State of India\'s Birds 2023, archived assessment table, Zenodo record '
                          '11124590 (https://zenodo.org/records/11124590). The recorded IUCN category is a '
                          'quotation of that snapshot, distinct from India-specific priority classifications.', small))
    flow.append(Paragraph('Frozen protocol SHA-256: ' + evidence['protocol_hash'] + '. '
                          'The saved protocol, dataset hash, model and adapter provenance, raw outputs, errors, '
                          'metric denominators, deadline amendment and paired analysis are retained in the '
                          'local reproducibility bundle. Public availability is not claimed without a release URL.', small))
    def footer(c, doc):
        c.saveState()
        c.setFont('Times-Roman', 9)
        c.drawCentredString(A4[0]/2, 14*mm, str(12 + doc.page))
        c.restoreState()
    doc.build(flow, onFirstPage=footer, onLaterPages=footer)
    return mem.getvalue()


def main():
    evidence = json.loads(EVIDENCE.read_text())
    if evidence['species'] != 60 or evidence['examples_per_method'] != 180:
        raise ValueError('incomplete or changed comparison')
    if evidence['primary']['eligible_species'] != 60 or evidence['primary']['excluded_species']:
        raise ValueError('incomplete primary analysis')
    summaries = summary_map(evidence)
    for m in ('constrained', 'qlora-42'):
        if summaries[(m, 'all')]['metrics']['outputs'] != 180:
            raise ValueError('missing test outputs')
    reader = PdfReader(SOURCE)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    edits = replacement_blocks(evidence, summaries)
    audit = []
    changed_pages = sorted({pn for pn, _ in edits})
    for pn in changed_pages:
        page = writer.pages[pn-1]
        stream, groups = text_groups(page, writer)
        by_id = {g['id']: g for g in groups}
        mem = BytesIO()
        overlay = canvas.Canvas(mem, pagesize=(float(page.mediabox.width), float(page.mediabox.height)))
        for (page_no, group_id), new_text in sorted(edits.items()):
            if page_no != pn:
                continue
            group = by_id[group_id]
            old_text = group['text']
            font = page['/Resources']['/Font'][group['font']]['/BaseFont'].removeprefix('/')
            size = group['size']
            leading = group['leading']
            lines = group['newlines']
            x, bottom = group['ctm'][4:6]
            old_height = lines*leading
            width = 165 if (pn, group_id) == (7,16) else (145 if pn == 12 and group_id in (3,4) else WIDTH)
            block_style = style(f'p{pn}g{group_id}', font, size, leading,
                                alignment=TA_JUSTIFY if size == 10.5 else TA_LEFT)
            paragraph = Paragraph(new_text, block_style)
            _, height = paragraph.wrap(width, 2000)
            if height > old_height + 0.05:
                raise ValueError(f'Page {pn} group {group_id}: replacement needs {height:.1f} pt, '
                                 f'original permits {old_height:.1f}; keep font and shorten wording')
            # Remove actual old text operators, rather than visually covering
            # searchable stale claims. Preserve all surrounding graphics/state.
            for index in range(group['begin'], group['end'] + 1):
                values, op = stream.operations[index]
                if op == b'Tj':
                    stream.operations[index] = ([TextStringObject('')], op)
                elif op == b'TJ':
                    stream.operations[index] = ([ArrayObject()], op)
            paragraph.drawOn(overlay, x, bottom + old_height - height)
            audit.append({'page': pn, 'group': group_id, 'font': font, 'font_size': size,
                          'leading': leading, 'old_height': old_height, 'new_height': height,
                          'rect_pdf': [x, bottom, x+width, bottom+old_height],
                          'original_text': old_text, 'replacement_text': new_text})
        page.replace_contents(stream)
        overlay.save()
        mem.seek(0)
        page.merge_page(PdfReader(mem).pages[0])
    appendix_reader = PdfReader(BytesIO(make_appendix(evidence, summaries)))
    for page in appendix_reader.pages:
        writer.add_page(page)
    metadata = dict(reader.metadata or {})
    metadata['/Subject'] = 'Minimal revision with completed matched QLoRA evaluation; original typography preserved'
    writer.add_metadata(metadata)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('wb') as handle:
        writer.write(handle)
    manifest = {
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_pdf': str(SOURCE), 'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'output_pdf': str(OUTPUT), 'output_sha256': hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
        'original_pages': 12, 'appendix_pages': len(appendix_reader.pages),
        'changed_original_pages': changed_pages, 'unchanged_original_pages': [x for x in range(1,13) if x not in changed_pages],
        'edits': audit, 'protocol_hash': evidence['protocol_hash'],
        'format_preservation': 'Original page content retained except listed text operators; all original images and graphics retained; standard Times fonts and sizes preserved',
    }
    (OUTPUT.parent / 'minimal_revision_manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps({'pdf': str(OUTPUT), 'pages': len(writer.pages), 'changed_blocks': len(audit)}, indent=2))


if __name__ == '__main__':
    main()
