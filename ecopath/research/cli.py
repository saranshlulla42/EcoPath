"""Run from ecopath: python3 -m research.cli --help."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from . import audit, dataset, fixtures, reporting, runner
from .contract import REPORT_SCHEMA, file_hash, read_jsonl, write_jsonl_new, write_new
from .statistics import paired_bootstrap


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('audit'); p.add_argument('--out',required=True)
    p=sub.add_parser('legacy-annotate'); p.add_argument('--out',required=True);p.add_argument('--seed',type=int,required=True)
    p=sub.add_parser('select-pilot'); p.add_argument('--records',required=True); p.add_argument('--out',required=True)
    p.add_argument('--count',type=int,default=30); p.add_argument('--seed',type=int,required=True)
    p=sub.add_parser('build'); p.add_argument('--records',required=True); p.add_argument('--out',required=True)
    p.add_argument('--seed',type=int,required=True); p.add_argument('--validation-fraction',type=float,required=True)
    p.add_argument('--test-fraction',type=float,required=True); p.add_argument('--partial-fraction',type=float,required=True)
    p.add_argument('--pilot-selection'); p.add_argument('--species-only',action='store_true')
    p=sub.add_parser('freeze'); p.add_argument('--config',required=True); p.add_argument('--dataset',required=True); p.add_argument('--out',required=True)
    p=sub.add_parser('run'); p.add_argument('--protocol',required=True); p.add_argument('--dataset',required=True); p.add_argument('--out',required=True)
    p.add_argument('--execute-models',action='store_true'); p.add_argument('--retry-errors',action='store_true')
    p.add_argument('--methods',nargs='+',help='run only these frozen method IDs; useful for fresh per-method GPU processes')
    p=sub.add_parser('summarize'); p.add_argument('--run',required=True); p.add_argument('--out',required=True)
    p=sub.add_parser('annotate'); p.add_argument('--run',required=True); p.add_argument('--dataset',required=True)
    p.add_argument('--out',required=True); p.add_argument('--seed',type=int,required=True)
    p=sub.add_parser('adjudicate'); p.add_argument('--reviews',nargs='+',required=True); p.add_argument('--out',required=True)
    p=sub.add_parser('annotation-summary');p.add_argument('--adjudication',required=True);p.add_argument('--out',required=True)
    p=sub.add_parser('statistics'); p.add_argument('--run',required=True); p.add_argument('--dataset',required=True)
    p.add_argument('--method-a',required=True); p.add_argument('--method-b',required=True)
    p.add_argument('--metric',default='structured_field_success_e2e'); p.add_argument('--draws',type=int,required=True)
    p.add_argument('--seed',type=int,required=True); p.add_argument('--out',required=True)
    p=sub.add_parser('smoke'); p.add_argument('--out',required=True)
    p=sub.add_parser('legacy-template'); p.add_argument('--audit-dir',required=True); p.add_argument('--out',required=True)
    p=sub.add_parser('schema'); p.add_argument('--out',required=True)
    args=parser.parse_args()
    if args.command=='audit':
        result=audit.extract(args.out)
    elif args.command=='legacy-annotate':
        result={'packets':audit.legacy_annotations(args.out,args.seed)}
    elif args.command=='select-pilot':
        result=dataset.select_pilot(read_jsonl(args.records),args.count,args.seed); write_new(args.out,result)
    elif args.command=='build':
        records=read_jsonl(args.records)
        pilot_ids=json.loads(Path(args.pilot_selection).read_text())['selected_ids'] if args.pilot_selection else []
        assignments=dataset.assign_splits(records,args.seed,args.validation_fraction,args.test_fraction,not args.species_only,pilot_ids)
        examples=dataset.build_dataset(records,assignments,args.seed,args.partial_fraction,group_genus=not args.species_only)
        out=Path(args.out)
        write_jsonl_new(out/'examples.PRIVATE.jsonl',examples)
        reporting.dataset_summary(examples,out/'composition.json')
        # Separate model payloads contain no expected values, hidden references or split metadata.
        write_jsonl_new(out/'model_payloads.jsonl',[e['payload'] for e in examples])
        write_jsonl_new(out/'training.PRIVATE.jsonl',[e for e in examples if e['split'] in {'train','validation'}])
        for split in ('train','validation','pilot','test'):
            write_jsonl_new(out/f'{split}.PRIVATE.jsonl',[e for e in examples if e['split']==split])
        for e in examples:
            visible={s['source_id'] for s in e['payload']['sources']}
            original={s['source_id']:s for s in e['private_reference']['provenance']}
            catalog=[]
            for sid in visible:
                source=original[e['private_reference']['source_map'][sid]]
                catalog.append(dict(source,source_id=sid))
            # Filenames use only a digest; species IDs are data, never paths.
            from .contract import digest
            write_new(out/'review_packets'/f"{digest(e['example_id'])[:24]}.json",{'payload':e['payload'],'source_catalog':catalog})
        write_new(out/'splits.json',{'assignments':assignments,'seed':args.seed,'group_genus':not args.species_only,
                                    'validation_fraction':args.validation_fraction,'test_fraction':args.test_fraction,
                                    'records_sha256':file_hash(args.records),'partial_fraction':args.partial_fraction,
                                    'pilot_ids':pilot_ids})
        result={'examples':len(examples),'species':len(records)}
    elif args.command=='freeze':
        result=runner.freeze(args.config,args.dataset,args.out)
    elif args.command=='run':
        result={'latest_records':len(runner.run(args.protocol,args.dataset,args.out,args.execute_models,args.retry_errors,
                                                method_ids=args.methods))}
    elif args.command=='summarize':
        result={'groups':len(reporting.summarize(args.run,args.out))}
    elif args.command=='annotate':
        result={'packets':reporting.annotation_export(args.run,args.dataset,args.out,args.seed)}
    elif args.command=='adjudicate':
        result={'packets':len(reporting.adjudicate(args.reviews,args.out))}
    elif args.command=='annotation-summary':
        result=reporting.annotation_summary(args.adjudication,args.out)
    elif args.command=='statistics':
        rows=list(runner.latest_attempts(read_jsonl(args.run)).values())
        methods=(args.method_a,args.method_b)
        examples=read_jsonl(args.dataset)
        manifest=json.loads(Path(args.run+'.manifest.json').read_text())
        families={m:([x for x in manifest['methods'] if x['method']==m] if m in runner.METHODS
                     else [x for x in manifest['methods'] if x['id']==m]) for m in methods}
        seeds={m:[x.get('training_seed') for x in family] for m,family in families.items()}
        if any(not v for v in seeds.values()):
            raise ValueError('comparison method absent from frozen protocol')
        converted=[]
        for row in rows:
            for m,family in families.items():
                if row['method_id'] in {x['id'] for x in family}:
                    converted.append(dict(row,method=m))
        # Compare only the frozen run split, including failures and planned missing cells.
        protocol_hashes={r['protocol_hash'] for r in rows}
        if len(protocol_hashes)!=1 or manifest['protocol_hash'] not in protocol_hashes:
            raise ValueError('statistics require one frozen protocol')
        examples=[e for e in examples if e['example_id'] in manifest['planned_examples']]
        result=paired_bootstrap(converted,examples,*methods,args.metric,seeds,args.draws,args.seed)
        write_new(args.out,result)
    elif args.command=='schema':
        write_new(args.out,REPORT_SCHEMA); result={'schema':args.out}
    else:
        out=Path(args.out)
        out.mkdir(parents=True,exist_ok=True)
        if args.command=='smoke':
            records=fixtures.records()
            phase='synthetic-fixture'
        else:
            records=read_jsonl(Path(args.audit_dir)/'legacy_diagnostic_records.jsonl')
            phase='legacy-diagnostic'
        assignments={r['species_id']:'pilot' for r in records}
        examples=dataset.build_dataset(records,assignments,42,.5)
        reporting.dataset_summary(examples,out/'composition.json')
        path=out/'examples.PRIVATE.jsonl'
        write_jsonl_new(path,examples)
        config=out/'config.json'; write_new(config,fixtures.template_config(phase))
        protocol=out/'protocol.json'; runner.freeze(config,path,protocol)
        run_path=out/'run.jsonl'; runner.run(protocol,path,run_path)
        reporting.summarize(run_path,out/'results')
        reporting.annotation_export(run_path,path,out/'annotation',42)
        result={'phase':phase,'species':len(records),'outputs':len(examples),'model_inference_executed':False}
    print(json.dumps(result,indent=2,ensure_ascii=False))


if __name__=='__main__':
    main()
