"""Finish analysis and the minimal PDF revision when the two GPU arms finish.

This supervisor does not start or modify inference. It preserves a status file
and logs so the authorized submission work survives a conversation interruption.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / 'research/paper_revision'
RUN = ROOT / 'research/artifacts/final-qwen-a09a354-v1/run.jsonl'
RUNTIME = Path('/home/saranshlulla/.cache/codex-runtimes/codex-primary-runtime/dependencies')
MARKER = Path('/home/saranshlulla/.codex/plugins/cache/openai-primary-runtime/pdf/26.1025.11240/skills/pdf/container_tools/mark_artifact_operation_started.mjs')
STATUS = WORK / 'submission_status.json'


def save_status(state, **details):
    data = dict(state=state, updated_at_utc=datetime.now(timezone.utc).isoformat(), pid=os.getpid(), **details)
    temporary = STATUS.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2))
    temporary.replace(STATUS)
    print(json.dumps(data), flush=True)


def run_logged(command, name):
    with (WORK / name).open('w') as log:
        result = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'{name}: command exited {result.returncode}; inspect saved log')


def main():
    previous = None
    while True:
        counts = Counter()
        errors = Counter()
        latest = {}
        for line in RUN.open():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            latest[(row['method_id'], row['example_id'])] = row
        for row in latest.values():
            counts[row['method_id']] += 1
            if row['error']:
                errors[row['method_id']] += 1
        progress = (dict(counts), dict(errors))
        if progress != previous:
            save_status('waiting_for_matched_evaluation', counts=dict(counts), errors=dict(errors))
            previous = progress
        if all(counts[method] == 180 for method in ('constrained', 'qlora-42')):
            if any(errors[method] for method in ('constrained', 'qlora-42')):
                raise RuntimeError('execution errors in matched arms; preserve them and inspect before final paper generation')
            break
        time.sleep(30)
    save_status('computing_paired_results', counts=dict(counts))
    run_logged([str(ROOT/'backend/.venv/bin/python'), str(WORK/'collect_reduced_results.py')], 'analysis.log')
    save_status('preparing_minimal_pdf', counts=dict(counts))
    marker_flag = WORK / 'pdf_artifact_operation_started.json'
    if not marker_flag.exists() and MARKER.exists():
        subprocess.run([str(RUNTIME/'node/bin/node'), str(MARKER), '--operation-kind', 'edit',
                        '--expected-output-count', '1', '--output-format', 'pdf'], check=True, cwd=ROOT)
        marker_flag.write_text(json.dumps({'at_utc': datetime.now(timezone.utc).isoformat(), 'operation': 'edit'}))
    run_logged([str(RUNTIME/'python/bin/python3'), str(WORK/'build_minimal_revision.py')], 'pdf_build.log')
    save_status('pdf_generated_pending_visual_verification', counts=dict(counts),
                output=str(ROOT/'output/pdf/EcoPath_Paper_Minimal_Revision.pdf'))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        save_status('needs_attention', error=f'{type(exc).__name__}: {exc}')
        raise
