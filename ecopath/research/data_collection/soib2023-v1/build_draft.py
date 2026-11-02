"""Offline extraction of a provisional, source-backed SoIB pilot.

Run with system Python from ecopath. Inputs are the checksum-verified, published
Zenodo v1 India table and its captured metadata. No retrieval or model calls.
Human review flags are deliberately not upgraded to verified.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from research.contract import FIELDS, canonical, digest, read_jsonl, validate_record, write_jsonl_new, write_new
from research.dataset import make_variant, validate_examples
from research.reporting import dataset_summary

HERE=Path(__file__).resolve().parent
VERSION='soib2023-web-draft-v1'
SEED=42
COUNT=30
DOI='10.5281/zenodo.11124590'
SOURCE_URL='https://zenodo.org/records/11124590/files/SoIB%202023%20India.csv?download=1'


def extract(row,index,retrieved):
    scientific=row['Scientific Name'].strip()
    species_id='soib2023:'+scientific.replace(' ','_')
    fields={field:{'value':None,'availability':'missing','source_ids':[]} for field in FIELDS}
    sources=[]
    def add(field,columns,value):
        source_id=f'soib2023:india:record-{index}:{field}'
        excerpt='; '.join(f'{key}={row[key]}' for key in columns)
        fields[field]={'value':value,'availability':'available','source_ids':[source_id]}
        sources.append({'source_id':source_id,
            'record_id':f'{DOI}/SoIB 2023 India.csv; data-record={index}; scientific-name={scientific}',
            'url':SOURCE_URL,'retrieved_at':retrieved,'excerpt':excerpt,
            'field':field,'value':value,'license':'MIT; Zenodo record 11124590 metadata; attribution retained in LICENSE.txt',
            'extraction_review':'automated_pending_human'})
    long_key='SoIB 2023 Long-term Trend Status'
    current_key='SoIB 2023 Current Annual Trend Status'
    if row[long_key] not in {'','NA'} or row[current_key] not in {'','NA'}:
        # Report the source's uncertainty classifications too; they are not
        # evidence of an ecological increase/decline. Scope stays in the value.
        add('population_trend',[long_key,current_key],
            f"India; SoIB 2023 assessment: long-term trend={row[long_key]}; current annual trend={row[current_key]}.")
    mappings=[('range_summary','SoIB 2023 Distribution Range Size Status','distribution range-size category'),
              ('habitat','Habitat Specialization','habitat specialization classification'),
              ('diet','Diet Guild','diet-guild classification'),
              ('migratory_behavior','Migratory Status within India','migratory-status classification within India')]
    for field,column,label in mappings:
        if row[column] not in {'','NA'}:
            add(field,[column],f"SoIB 2023 {label}: {row[column]}.")
    # Do not map priority/regional Red List status to official global IUCN
    # categories, 1% thresholds to population size, activity periods to breeding
    # phenology, or generic report threats to species-specific threat facts.
    result={'species_id':species_id,'scientific_name':scientific,'genus':scientific.split()[0],
            'taxonomy':{'common_name':row['English Name'],'family':row['Family'],'order':row['Order'],
                        'source_record':f'{DOI}:india-record-{index}'},
            'dataset_version':VERSION,
            'sampling':{'country_code':'IN','frame_source_url':'https://zenodo.org/records/11124590',
                        'membership_review':'source_checked_pending_human',
                        'source_selected_for_soib':row['Selected for SoIB'],
                        'source_current_trend_stratum':row[current_key],
                        'source_version':'2023 report, Zenodo v1; not a current 2026 assessment',
                        'selection':'seeded current-trend-category round robin; one species per genus; exact legacy-name exclusion'},
            'fields':fields,'sources':sources}
    validate_record(result)
    return result


def main():
    metadata=json.loads((HERE/'zenodo-record.json').read_text())
    source_file=next(f for f in metadata['files'] if f['key']=='SoIB 2023 India.csv')
    expected=source_file['checksum'].split(':',1)[1]
    assert hashlib.md5((HERE/'india.csv').read_bytes()).hexdigest()==expected
    retrieved=next(f['retrieved_at'] for f in json.loads((HERE/'download_manifest.json').read_text()) if f['file']=='india.csv')
    rows=list(csv.DictReader((HERE/'india.csv').open(encoding='utf-8-sig',newline='')))
    legacy={r['scientific_name'].casefold() for r in read_jsonl(ROOT/'research/artifacts/original/audit/species_inventory.jsonl')}
    exclusions=[];candidates=[]
    for index,row in enumerate(rows,1):
        name=row['Scientific Name'].strip()
        reason='not_selected_for_SoIB_2023' if row['Selected for SoIB']!='TRUE' else 'exact_name_in_legacy_experiment' if name.casefold() in legacy else None
        if reason:
            exclusions.append({'data_record':index,'scientific_name':name,'reason':reason});continue
        candidates.append((row,index))
    rng=random.Random(SEED)
    strata=defaultdict(list)
    for row,index in sorted(candidates,key=lambda pair:pair[0]['Scientific Name']):
        strata[row['SoIB 2023 Current Annual Trend Status']].append((row,index))
    for values in strata.values():rng.shuffle(values)
    keys=sorted(strata);rng.shuffle(keys)
    chosen=[];genera=set()
    while len(chosen)<COUNT and any(strata.values()):
        for key in keys:
            while strata[key]:
                row,index=strata[key].pop()
                genus=row['Scientific Name'].split()[0]
                if genus in genera:continue
                chosen.append((row,index));genera.add(genus);break
            if len(chosen)==COUNT:break
    records=[extract(row,index,retrieved) for row,index in chosen]
    assert len(records)==COUNT and len(genera)==COUNT
    write_jsonl_new(HERE/'pilot_records.DRAFT.jsonl',records)
    write_jsonl_new(HERE/'selected_source_rows.jsonl',[{'data_record':index,'source_row':row,'row_sha256':digest(row)} for row,index in chosen])
    write_jsonl_new(HERE/'sampling_exclusions.jsonl',exclusions)
    queue=[{'species_id':r['species_id'],'scientific_name':r['scientific_name'],'field':s['field'],
            'proposed_value':s['value'],'source_excerpt':s['excerpt'],'source_url':s['url'],
            'source_record_id':s['record_id'],'reviewer_id':None,'decision':None,'rationale':None}
           for r in records for s in r['sources']]
    write_jsonl_new(HERE/'extraction_review_queue.jsonl',queue)
    variants=[make_variant(r,level,'pilot',SEED,.5) for r in records for level in ('complete','partial','minimal')]
    validate_examples(variants)
    write_jsonl_new(HERE/'provisional_variants.PRIVATE.jsonl',variants)
    write_jsonl_new(HERE/'model_payloads.DRAFT.jsonl',[e['payload'] for e in variants])
    dataset_summary(variants,HERE/'composition.json')
    with (HERE/'pilot_overview.csv').open('x',newline='') as handle:
        writer=csv.writer(handle)
        writer.writerow(['species_id','scientific_name','common_name','genus','family','current_trend_stratum','available_fields','missing_fields','review'])
        for r in records:
            writer.writerow([r['species_id'],r['scientific_name'],r['taxonomy']['common_name'],r['genus'],r['taxonomy']['family'],
                r['sampling']['source_current_trend_stratum'],
                ';'.join(f for f,e in r['fields'].items() if e['availability']=='available'),
                ';'.join(f for f,e in r['fields'].items() if e['availability']=='missing'),'pending_human'])
    write_new(HERE/'collection_summary.json',{'phase':'source-backed-draft-collection','source_doi':DOI,
        'publication_date':metadata['metadata']['publication_date'],'zenodo_metadata_license':metadata['metadata']['license'],
        'raw_rows':len(rows),'source_selected_species':sum(r['Selected for SoIB']=='TRUE' for r in rows),
        'eligible_after_exact_legacy_name_exclusion':len(candidates),'exclusion_counts':dict(Counter(r['reason'] for r in exclusions)),
        'selected_species':len(records),'selected_genera':len(genera),'seed':SEED,
        'selection':'round robin across published current annual trend categories, one species per genus',
        'selected_strata':dict(Counter(r['sampling']['source_current_trend_stratum'] for r in records)),
        'source_assertions':len(queue),'variants':len(variants),'extraction_review':'pending_human',
        'schema_and_deterministic_variant_checks':'passed','published_md5_matches':True,
        'model_generation_executed':False,'ready_for_frozen_pilot':False,
        'limits':['single published source; 2023 snapshot, not current 2026 ecology',
                  'non-representative category-balanced sample; exact name matching does not resolve synonyms',
                  'source taxonomy and classifications quoted without independent field verification',
                  'global IUCN category, total population size, breeding behavior and species threats left missing',
                  'human extraction/sampling review and independent validation species still required']})
    print(f'{len(records)} source-backed draft species; {len(queue)} assertions; {len(variants)} provisional variants; human review pending')


if __name__=='__main__':main()
