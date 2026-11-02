/**
 * What each query cost.
 *
 * The claim this stage makes is that most queries never reach a model. That is
 * only worth making if it is measured, so every query records two independent
 * facts: whether the agent was called, and whether any network request happened
 * at all. They are different questions — `migration <species>` avoids the model
 * but still fetches precomputed data, while `help` and a disambiguation prompt
 * touch nothing.
 *
 * Counters live in memory and, best-effort, in localStorage so a session's
 * ratio survives a reload. Nothing is sent anywhere.
 */

export type Outcome =
  /** Parsed and executed from the registry. */
  | 'command'
  /** Ranked candidates shown; the user picks. */
  | 'disambiguate'
  /** Handed to the agent. */
  | 'fallback'
  /** Empty or unusable input. */
  | 'empty';

export interface QueryRecord {
  input: string;
  outcome: Outcome;
  verb: string | null;
  /** True when the research agent was invoked. */
  llmCalled: boolean;
  /** True when any HTTP request was made, model or not. */
  networkCalled: boolean;
  parseMs: number;
  totalMs: number;
  at: number;
}

const STORAGE_KEY = 'ecopath.command.telemetry.v1';
const MAX_RECORDS = 500;

let records: QueryRecord[] = [];

function persist(): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(records.slice(-MAX_RECORDS)));
  } catch {
    // Private windows and blocked storage are fine; the in-memory counters
    // still work for the current session.
  }
}

export function load(): void {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) records = JSON.parse(raw) as QueryRecord[];
  } catch {
    records = [];
  }
}

export function record(entry: Omit<QueryRecord, 'at'>): QueryRecord {
  const full: QueryRecord = { ...entry, at: Date.now() };
  records.push(full);
  if (records.length > MAX_RECORDS) records = records.slice(-MAX_RECORDS);
  persist();
  return full;
}

export interface Stats {
  total: number;
  /** Queries that never invoked the agent. This is the headline number. */
  withoutLLM: number;
  withoutLLMPct: number;
  /** Queries that made no HTTP request at all. */
  withoutNetwork: number;
  withoutNetworkPct: number;
  byOutcome: Record<Outcome, number>;
  byVerb: Record<string, number>;
  medianParseMs: number;
  medianTotalMs: number;
}

function median(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)];
}

export function stats(): Stats {
  const total = records.length;
  const withoutLLM = records.filter(r => !r.llmCalled).length;
  const withoutNetwork = records.filter(r => !r.networkCalled).length;

  const byOutcome = { command: 0, disambiguate: 0, fallback: 0, empty: 0 } as Record<Outcome, number>;
  const byVerb: Record<string, number> = {};
  for (const r of records) {
    byOutcome[r.outcome] += 1;
    if (r.verb) byVerb[r.verb] = (byVerb[r.verb] ?? 0) + 1;
  }

  return {
    total,
    withoutLLM,
    withoutLLMPct: total ? withoutLLM / total : 0,
    withoutNetwork,
    withoutNetworkPct: total ? withoutNetwork / total : 0,
    byOutcome,
    byVerb,
    medianParseMs: median(records.map(r => r.parseMs)),
    medianTotalMs: median(records.map(r => r.totalMs)),
  };
}

export function all(): readonly QueryRecord[] {
  return records;
}

export function reset(): void {
  records = [];
  persist();
}

/** One-line summary for the help panel or a debug corner. */
export function summary(): string {
  const s = stats();
  if (!s.total) return 'No queries yet.';
  return (
    `${s.total} queries — ${(s.withoutLLMPct * 100).toFixed(1)}% answered without the agent, ` +
    `${(s.withoutNetworkPct * 100).toFixed(1)}% with no network at all ` +
    `(median parse ${s.medianParseMs.toFixed(2)}ms)`
  );
}
