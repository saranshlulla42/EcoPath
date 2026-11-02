#!/usr/bin/env python
"""Read the token metrics collected by the agent loop.

    python evaluation/token_report.py                 # the whole picture
    python evaluation/token_report.py --per-turn      # one row per user query
    python evaluation/token_report.py --label followup_species
    python evaluation/token_report.py --since 2026-09-01
    python evaluation/token_report.py --sql "select ..."   # ad-hoc

The stage breakdown answers "tokens per user query, by stage". Input stages sum
to the provider's real input total; the split between them is computed locally
(see token_logger.TOKEN_SOURCE) and rescaled to that total, so the totals are
exact and only the split is approximate.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from agent import token_store  # noqa: E402

STAGES = [
    ("system_base", "system prompt (stable head)"),
    ("system_coverage", "system prompt (coverage block)"),
    ("system_context", "system prompt (session context)"),
    ("tool_schemas", "tool schemas"),
    ("history", "conversation history"),
    ("assistant_msgs", "assistant messages (loop)"),
    ("user_msg", "user message"),
    ("tool_results", "tool results"),
]


def _where(args) -> tuple[str, list]:
    clauses, params = [], []
    if args.label:
        clauses.append("t.label = ?")
        params.append(args.label)
    if args.since:
        clauses.append("t.ts >= ?")
        params.append(args.since)
    return (("WHERE " + " AND ".join(clauses)) if clauses else ""), params


def _bar(frac: float, width: int = 28) -> str:
    n = int(round(frac * width))
    return "█" * n + "·" * (width - n)


def summary(args) -> None:
    where, params = _where(args)
    rows = token_store.query(f"SELECT * FROM turn_stage_rollup t {where}", tuple(params))
    if not rows:
        print("No turns recorded yet. Run: python evaluation/replay.py --yes")
        return

    n = len(rows)
    tot = {k: sum(r[k] or 0 for r in rows) for k, _ in STAGES}
    input_total = sum(r["input_total"] or 0 for r in rows)
    generation = sum(r["generation"] or 0 for r in rows)
    cached = sum(r["cached"] or 0 for r in rows)
    total_tokens = input_total + generation
    rounds = sum(r["rounds"] or 0 for r in rows)

    print("=" * 74)
    print(f"  TOKEN REPORT — {n} user queries, {rounds} API calls")
    print("=" * 74)

    print(f"\n  input tokens        {input_total:>10,}   ({input_total / n:,.0f} per query)")
    print(f"  output tokens       {generation:>10,}   ({generation / n:,.0f} per query)")
    print(f"  total               {total_tokens:>10,}   ({total_tokens / n:,.0f} per query)")
    if input_total:
        print(f"  cached input        {cached:>10,}   ({cached / input_total:.1%} of input)")
        # Groq bills cached input at 50%.
        print(f"  billable-equiv in   {input_total - cached // 2:>10,}   (cached at 50%)")

    print(f"\n  INPUT BY STAGE (per query avg, share of input)")
    print(f"  {'stage':<34}{'tokens':>10}  {'avg':>8}  share")
    for key, label in STAGES:
        v = tot[key]
        frac = v / input_total if input_total else 0
        print(f"  {label:<34}{v:>10,}  {v / n:>8,.0f}  {frac:6.1%} {_bar(frac)}")
    attributed = sum(tot.values())
    print(f"  {'—' * 34}{attributed:>10,}  {attributed / n:>8,.0f}  {attributed / input_total if input_total else 0:6.1%}")
    print(f"\n  generation (output)               {generation:>10,}  {generation / n:>8,.0f}")

    # Fixed floor: what a query costs before any history or tool result exists.
    floor = token_store.query(
        f"""SELECT AVG(c.input_tokens) a, MIN(c.input_tokens) lo, MAX(c.input_tokens) hi, COUNT(*) n
            FROM api_calls c JOIN turns t USING(request_id) {where}
            AND c.round_index = 0 AND c.seg_history = 0"""
        if where
        else """SELECT AVG(c.input_tokens) a, MIN(c.input_tokens) lo, MAX(c.input_tokens) hi, COUNT(*) n
                FROM api_calls c JOIN turns t USING(request_id)
                WHERE c.round_index = 0 AND c.seg_history = 0""",
        tuple(params),
    )
    if floor and floor[0]["n"]:
        f = floor[0]
        print(f"\n  FIXED FLOOR (round 0, no history): avg {f['a']:,.0f}  range {f['lo']:,}–{f['hi']:,}  (n={f['n']})")

    # Resend: how much of the bill is the loop re-sending earlier context.
    rs = token_store.query(
        f"SELECT AVG(t.resend_multiplier) a, MAX(t.resend_multiplier) hi FROM turns t {where or ''}",
        tuple(params),
    )
    if rs and rs[0]["a"]:
        print(f"  RESEND MULTIPLIER: avg {rs[0]['a']:.2f}x  worst {rs[0]['hi']:.2f}x")

    # Tool results: the other candidate sink.
    tools = token_store.query(
        f"""SELECT ti.name, COUNT(*) calls, SUM(ti.est_tokens) tok, MAX(ti.est_tokens) worst,
                   MAX(ti.row_count) max_rows, SUM(ti.truncated) truncs,
                   SUM(CASE WHEN ti.error IS NOT NULL THEN 1 ELSE 0 END) errs,
                   AVG(ti.latency_ms) ms
            FROM tool_invocations ti JOIN turns t USING(request_id) {where}
            GROUP BY ti.name ORDER BY tok DESC""",
        tuple(params),
    )
    if tools:
        print(f"\n  TOOL RESULTS")
        print(f"  {'tool':<22}{'calls':>6}{'tokens':>9}{'worst':>8}{'rows':>7}{'trunc':>7}{'err':>5}{'ms':>7}")
        for r in tools:
            print(
                f"  {r['name']:<22}{r['calls']:>6}{r['tok'] or 0:>9,}{r['worst'] or 0:>8,}"
                f"{r['max_rows'] if r['max_rows'] is not None else '-':>7}"
                f"{r['truncs'] or 0:>7}{r['errs'] or 0:>5}{r['ms'] or 0:>7.0f}"
            )

    errs = token_store.query(
        f"SELECT t.label, t.error FROM turns t {where + ' AND' if where else 'WHERE'} t.error IS NOT NULL",
        tuple(params),
    )
    if errs:
        print(f"\n  FAILED TURNS: {len(errs)}")
        for e in errs:
            print(f"    {e['label'] or '-':<24} {e['error']}")


def per_turn(args) -> None:
    where, params = _where(args)
    rows = token_store.query(
        f"SELECT * FROM turn_stage_rollup t {where} ORDER BY t.ts", tuple(params)
    )
    if not rows:
        print("No turns recorded yet.")
        return
    print(f"  {'scenario':<22}{'rnd':>4}{'input':>8}{'out':>7}{'sys':>7}{'schema':>8}{'hist':>7}{'tools':>7}{'cache':>7}  query")
    for r in rows:
        print(
            f"  {(r['label'] or '-'):<22}{r['rounds']:>4}{r['input_total'] or 0:>8,}{r['generation'] or 0:>7,}"
            f"{r['system_prompt'] or 0:>7,}{r['tool_schemas'] or 0:>8,}{r['history'] or 0:>7,}"
            f"{r['tool_results'] or 0:>7,}{r['cached'] or 0:>7,}  {(r['user_message'] or '')[:44]}"
        )


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--per-turn", action="store_true", help="one row per user query")
    p.add_argument("--label", help="filter to one replay scenario")
    p.add_argument("--since", help="ISO timestamp lower bound, e.g. 2026-09-01")
    p.add_argument("--sql", help="run an arbitrary read-only query and print rows")
    args = p.parse_args()

    print(f"db: {token_store.DB_PATH}\n")
    if args.sql:
        for row in token_store.query(args.sql):
            print(dict(row))
        return 0
    if args.per_turn:
        per_turn(args)
    else:
        summary(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
