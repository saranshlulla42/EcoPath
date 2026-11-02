#!/usr/bin/env python
"""Replay the representative queries against the live agent to collect real
token numbers.

This makes REAL calls to the model provider — it costs tokens and is subject to
rate limits. Nothing about the agent's behaviour changes; the run just fills the
token metrics tables, tagged with each scenario's name.

    python evaluation/replay.py --dry-run          # show the plan, call nothing
    python evaluation/replay.py --yes              # run all 20 turns
    python evaluation/replay.py --scenario adhoc_sql --yes
    python evaluation/replay.py --yes --delay 2.0  # gentler on rate limits

Then read the numbers with:

    python evaluation/token_report.py

Caveat worth knowing before you interpret a second run: Groq caches prompt
prefixes for 2 hours, so replaying the same set twice inside that window will
show inflated cache hit rates versus a cold start. `cache_hit_rate` in the
report makes that visible rather than silent.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import replay_queries as rq  # noqa: E402


async def run_scenario(scenario: rq.Scenario, delay: float, verbose: bool, tag: str = "") -> list[dict]:
    from agent.agent_loop import run_agent_turn, reset_agent_session

    # One fresh session per scenario: a single-turn scenario then measures the
    # true fixed floor, and a multi-turn one accumulates history the way real
    # use does.
    session_id = f"replay-{scenario.name}-{uuid.uuid4().hex[:8]}"
    out = []
    for i, message in enumerate(scenario.turns):
        t0 = time.perf_counter()
        error = None
        try:
            label = f"{tag}:{scenario.name}" if tag else scenario.name
            result = await run_agent_turn(message, session_id, label=label)
            request_id = result.request_id
            n_blocks = len(result.blocks)
        except Exception as e:  # a failed turn is data too; keep going
            request_id, n_blocks, error = None, 0, f"{type(e).__name__}: {e}"
        elapsed = time.perf_counter() - t0
        out.append(
            {
                "scenario": scenario.name,
                "turn": i,
                "message": message,
                "request_id": request_id,
                "blocks": n_blocks,
                "seconds": round(elapsed, 2),
                "error": error,
            }
        )
        status = "ERR " if error else "ok  "
        print(f"  {status} t{i} {elapsed:6.2f}s  {message[:64]}")
        if error and verbose:
            print(f"       {error}")
        if delay:
            await asyncio.sleep(delay)

    reset_agent_session(session_id)
    return out


async def main_async(args) -> int:
    scenarios = rq.SCENARIOS
    if args.scenario:
        picked = [rq.by_name(n) for n in args.scenario]
        missing = [n for n, s in zip(args.scenario, picked) if s is None]
        if missing:
            print(f"unknown scenario(s): {', '.join(missing)}", file=sys.stderr)
            return 2
        scenarios = [s for s in picked if s]

    turns = sum(len(s.turns) for s in scenarios)
    print(f"{len(scenarios)} scenarios, {turns} turns, model calls are real.")
    for s in scenarios:
        print(f"  {s.name:22} {len(s.turns)} turn(s)  — {s.intent}")

    if args.dry_run:
        print("\ndry run: nothing called.")
        return 0

    if not args.yes:
        reply = input(f"\nRun {turns} live turns against the model? [y/N] ").strip().lower()
        if reply not in ("y", "yes"):
            print("aborted.")
            return 1

    from agent import token_store

    print(f"\nwriting metrics to {token_store.DB_PATH}")
    if not token_store.ENABLED:
        print("WARNING: ECOPATH_TOKEN_METRICS is off — nothing will be recorded.")

    t0 = time.perf_counter()
    results = []
    for s in scenarios:
        print(f"\n[{s.name}]")
        results.extend(await run_scenario(s, args.delay, args.verbose, args.tag))

    failed = [r for r in results if r["error"]]
    print(f"\n{len(results)} turns in {time.perf_counter() - t0:.1f}s, {len(failed)} failed.")
    for r in failed:
        print(f"  FAILED {r['scenario']} t{r['turn']}: {r['error']}")
    print("\nnow run:  python evaluation/token_report.py")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="list the plan without calling the model")
    p.add_argument("--yes", "-y", action="store_true", help="skip the confirmation prompt")
    p.add_argument("--scenario", action="append", help="run only this scenario (repeatable)")
    p.add_argument("--delay", type=float, default=1.0, help="seconds between turns (rate limiting), default 1.0")
    p.add_argument("--tag", default="", help="prefix labels with this run tag, e.g. --tag before")
    p.add_argument("--verbose", "-v", action="store_true", help="print full error text")
    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
