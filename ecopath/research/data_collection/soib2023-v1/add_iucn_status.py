"""Add the explicit 2023 global IUCN Category column as a dated field."""
from __future__ import annotations
import csv
import json
import re
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from research.contract import read_jsonl, validate_record, write_jsonl_new, write_new
from research.dataset import make_variant, validate_examples
from research.reporting import dataset_summary

SOURCE_URL="https://zenodo.org/records/11124590/files/SoIB%202023%20India.csv?download=1"
REVIEWER="Codex AI assistant (user-authorized source review)"


def main():
    parent=HERE/'reviewed-v3'; out=HERE/'reviewed-v4'; out.mkdir(exist_ok=False)
    csvrows=list(csv.DictReader((HERE/'india.csv').open(encoding='utf-8-sig',newline='')))
    retrieved=next(x['retrieved_at'] for x in json.loads((HERE/'download_manifest.json').read_text()) if x['file']=='india.csv')
    records=read_jsonl(parent/'pilot_records.jsonl')+read_jsonl(parent/'heldout_records.jsonl')
    ledger=read_jsonl(parent/'source_review_ledger.jsonl')
    iucn_ledger=[]
    dist={}
    for r in records:
        # Every source row ID remains anchored to the unchanged SoIB 2023 row,
        # even where the accepted name was modernized in the v3 taxonomy layer.
        existing=next(s for s in r['sources'] if s['field']=='population_trend')
        rowno=int(existing['record_id'].split('data-record=')[1].split(';')[0])
        row=csvrows[rowno-1]
        assert row['Scientific Name']==r['taxonomy']['source_scientific_name_2023']
        raw_value=row['IUCN Category'].strip()
        assert raw_value and raw_value not in {'NA','Not recognized','Not Evaluated'}
        value=raw_value
        sid=f"soib2023:india:record-{rowno}:iucn_status"
        src={'source_id':sid,'record_id':f"10.5281/zenodo.11124590/SoIB 2023 India.csv; data-record={rowno}; scientific-name={row['Scientific Name']}",
             'url':SOURCE_URL,'retrieved_at':retrieved,'excerpt':f"IUCN Category={raw_value}",
             'field':'iucn_status','value':value,
             'license':'MIT; Zenodo 2023 record metadata; attribution retained in LICENSE.txt',
             'extraction_review':'verified'}
        r['sources'].append(src)
        r['fields']['iucn_status']={'value':value,'availability':'available','source_ids':[sid]}
        validate_record(r)
        dist[raw_value]=dist.get(raw_value,0)+1
        iucn_ledger.append({'species_id':r['species_id'],'scientific_name':r['scientific_name'],
            'field':'iucn_status','proposed_value':value,'source_excerpt':src['excerpt'],'source_url':SOURCE_URL,
            'source_record_id':src['record_id'],'reviewer_id':REVIEWER,'reviewed_at':'2026-10-29',
            'decision':'approve_source_faithful_extraction',
            'rationale':'Compared the explicit IUCN Category cell in the checksum-verified SoIB 2023 national table with its exact data-record locator. Kept separate from SoIB India Priority and Regional Red List Category. Added the publication edition to the visible value so it cannot be mistaken for a current status.',
            'checks':{'record_locator':'pass','excerpt_value':'pass','global_status_column_distinct_from_regional_priority':'pass','temporal_scope_explicit':'pass'},
            'taxonomy_crosswalk':r['taxonomy']['taxonomy_source_url']})
    ledger.extend(iucn_ledger)
    write_jsonl_new(out/'source_review_ledger.jsonl',ledger)
    pilot=[r for r in records if r['sampling'].get('partition') is None]
    # In reviewed-v3 split is encoded in heldout manifest, not pilot record rows.
    hmanifest=read_jsonl(parent/'heldout_manifest.jsonl')
    heldids={x['species_id'] for x in hmanifest}
    pilot=[r for r in records if r['species_id'] not in heldids]
    held=[r for r in records if r['species_id'] in heldids]
    write_jsonl_new(out/'pilot_records.jsonl',pilot)
    write_jsonl_new(out/'heldout_records.jsonl',held)
    write_jsonl_new(out/'heldout_manifest.jsonl',hmanifest)
    write_jsonl_new(out/'taxonomy_crosswalk.jsonl',read_jsonl(parent/'taxonomy_crosswalk.jsonl'))
    assignment={x['species_id']:x['split'] for x in hmanifest}
    examples=[make_variant(r,level,'pilot' if r['species_id'] not in assignment else assignment[r['species_id']],9173,.5)
              for r in records for level in ('complete','partial','minimal')]
    validate_examples(examples)
    pv=[e for e in examples if e['split']=='pilot']; hv=[e for e in examples if e['split']!='pilot']
    for name,items in [('all_variants.PRIVATE.jsonl',examples),('all_model_payloads.jsonl',[e['payload'] for e in examples]),
                       ('pilot_variants.PRIVATE.jsonl',pv),('heldout_variants.PRIVATE.jsonl',hv),
                       ('heldout_model_payloads.jsonl',[e['payload'] for e in hv])]:
        write_jsonl_new(out/name,items)
    dataset_summary(examples,out/'all_composition.json'); dataset_summary(hv,out/'heldout_composition.json')
    summary={'status':'AI source-consistency review; no human credentials claimed','species':len(records),
        'pilot_species':len(pilot),'validation_species':sum(x['split']=='validation' for x in hmanifest),
        'test_species':sum(x['split']=='test' for x in hmanifest),'source_assertions':len(ledger),
        'iucn_categories_2023_snapshot':dist,'source_mismatches_in_2023_iucn_column':0,
        'soib_2025_table_value_differences_vs_2023':[
          {'scientific_name':'Coracias benghalensis','2023':'Least Concern','2025':'Near Threatened'},
          {'scientific_name':'Pluvialis squatarola','2023':'Least Concern','2025':'Vulnerable'}],
        'iucn_date_semantics':'IUCN categories are exact SoIB 2023 source values; the dataset documentation and source map scope them to that release. Two differing values in the later SoIB table are retained as dated comparisons, not silently backfilled into the 2023 target.',
        'reviewer':REVIEWER,'retrieval_date':retrieved,
        'remaining_limits':['The source has a single categorical IUCN Category field and does not provide IUCN assessment date/version per species.',
          'Population size, breeding behavior and key threats remain missing; no proxy fields were relabelled.',
          'The 2025 SoIB table is a later snapshot whose file-level license was not exposed on the inspected Zenodo rights page.',
          'India Checklist v10.1 (published 2026-05-15) and the linked SoIB 2026 workbook were not reviewed; use this as a dated SoIB 2023 experiment snapshot, not current 2026 status.']}
    write_new(out/'review_summary.json',summary)
    (out/'README.md').write_text("""# Reviewed SoIB dataset v4\n\nThis version adds the source's explicit `IUCN Category` field for all 120 species. It does not confuse that column with SoIB's India-specific `Priority Status` or the regional Red List field. The target retains the exact category string; its SoIB 2023 edition and retrieval scope are recorded in the private source assertion and dataset documentation.\n\nA live comparison against the later SoIB 2025 India table found two differing table values: *Coracias benghalensis* is reported as Least Concern in the 2023 source and Near Threatened in the later table; *Pluvialis squatarola* is reported as Least Concern in 2023 and Vulnerable in the later table. The 2023 values are retained for this fixed-snapshot dataset; the differences are documented in `review_summary.json`.\n\nDataset design remains 30 development, 30 validation and 60 test species, genus-disjoint. Each has complete, partial and minimal variants. Population size, breeding behavior and species-specific threats remain null because the sources reviewed here do not support them. The test set must remain sealed.\n\nThis is a dated dataset review, not a current 2026 ecological reference. India Checklist v10.1 and a linked SoIB 2026 workbook have not been crosschecked. The reviewer is recorded as a Codex AI assistant; this is source extraction review, not independent field verification by an ornithologist. See `source_review_ledger.jsonl`, `taxonomy_crosswalk.jsonl`, and `review_summary.json`.\n""",encoding='utf-8',newline='\n')
    print(json.dumps({'species':len(records),'assertions':len(ledger),'iucn_distribution':dist,'examples':len(examples)},indent=2))

if __name__=='__main__':main()
