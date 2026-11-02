"""Summarize the authorized matched comparison only after both arms finish."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.contract import read_jsonl, write_new
from research.reporting import summarize
from research.runner import latest_attempts
from research.statistics import paired_bootstrap


def main():
    run = ROOT / 'research/artifacts/final-qwen-a09a354-v1/run.jsonl'
    dataset = ROOT / 'research/data_collection/soib2023-v1/reviewed-v4/all_variants.PRIVATE.jsonl'
    protocol_file = run.parent / 'protocol.json'
    protocol = json.loads(protocol_file.read_text())
    examples = [x for x in read_jsonl(dataset) if x['example_id'] in protocol['planned_examples']]
    expected = {x['example_id'] for x in examples}
    rows = list(latest_attempts(read_jsonl(run)).values())
    wanted = ('constrained', 'qlora-42')
    for method in wanted:
        selected = [x for x in rows if x['method_id'] == method]
        if {x['example_id'] for x in selected} != expected or len(selected) != 180:
            raise RuntimeError(f'{method} incomplete: {len(selected)}/180; no final paper results written')
        if any(x['protocol_hash'] != protocol['protocol_hash'] for x in selected):
            raise RuntimeError('mixed protocols')
    output = run.parent / 'reduced-summary'
    summaries = summarize(run, output)
    converted = [dict(x, method=x['method_id']) for x in rows if x['method_id'] in wanted]
    primary = paired_bootstrap(converted, examples, 'constrained', 'qlora-42',
                               'structured_field_success_e2e',
                               {'constrained': [None], 'qlora-42': [42]}, 2000, 42)
    if primary['status'] != 'computed' or primary['eligible_species'] != 60 or primary['excluded_species']:
        raise RuntimeError('primary comparison is not a complete 60-species paired grid')
    write_new(output / 'paired-field-success.json', primary)
    selected_summaries = [x for x in summaries if x['method_id'] in (*wanted, 'template')]
    selected_rows = [x for x in rows if x['method_id'] in wanted]
    details = {}
    for method in wanted:
        group = [x for x in selected_rows if x['method_id'] == method]
        details[method] = {
            'outputs': len(group),
            'errors': sum(bool(x['error']) for x in group),
            'truncated': sum(bool(x['result'].get('truncated')) for x in group),
            'total_wall_seconds': sum(x['result']['wall_seconds'] for x in group),
            'finish_reasons': dict(Counter(x['result'].get('finish_reason', 'unavailable') for x in group)),
        }
    evidence = {
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'scope': 'deadline-amended single-seed matched held-out comparison; other arms are not pooled',
        'protocol_hash': protocol['protocol_hash'],
        'dataset_sha256': protocol['dataset_sha256'],
        'run_sha256': hashlib.sha256(run.read_bytes()).hexdigest(),
        'species': 60, 'examples_per_method': 180,
        'methods': list(wanted), 'primary': primary,
        'summaries': selected_summaries, 'execution': details,
        'source_run': str(run), 'source_dataset': str(dataset),
    }
    write_new(output / 'paper-evidence.json', evidence)
    print(json.dumps({'out': str(output), 'primary': primary['estimate'],
                      'ci95': primary['ci95'], 'execution': details}, indent=2))


if __name__ == '__main__':
    main()
