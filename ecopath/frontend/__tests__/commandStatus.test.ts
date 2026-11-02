import { beforeEach, describe, expect, it } from 'vitest';
import {
  evidenceLine,
  migrationOutcome,
  statusLabel,
  type SpeciesStatus,
} from '../lib/commands/status';
import * as telemetry from '../lib/commands/telemetry';

function status(over: Partial<SpeciesStatus> = {}): SpeciesStatus {
  return {
    status: 'migratory',
    confidence: 0.9,
    insufficient_basis: null,
    total_records: 3600,
    months_with_data: 12,
    max_displacement_km: 1200,
    ...over,
  };
}

describe('migration responses are visibly different for each outcome', () => {
  const migratory = migrationOutcome('Amur Falcon', status());
  const resident = migrationOutcome(
    'Asian Koel',
    status({ status: 'resident', max_displacement_km: 388 }),
  );
  const sparse = migrationOutcome(
    'Sarus Crane',
    status({
      status: 'insufficient_data',
      insufficient_basis: 'coverage',
      total_records: 28,
      months_with_data: 2,
      max_displacement_km: 617,
    }),
  );
  const banded = migrationOutcome(
    'Common Iora',
    status({
      status: 'insufficient_data',
      insufficient_basis: 'inconclusive',
      max_displacement_km: 473,
    }),
  );

  it('gives every outcome its own kind', () => {
    const kinds = [migratory.kind, resident.kind, sparse.kind, banded.kind];
    expect(kinds).toEqual(['track', 'resident', 'insufficient', 'inconclusive']);
    expect(new Set(kinds).size).toBe(4);
  });

  it('only the migratory case renders a track', () => {
    expect(migratory.kind).toBe('track');
    for (const o of [resident, sparse, banded]) {
      expect(o.kind).not.toBe('track');
      expect('message' in o && o.message).toBeTruthy();
    }
  });

  it('says "resident" for a resident, and names the movement it did measure', () => {
    if (resident.kind !== 'resident') throw new Error('expected resident');
    expect(resident.message).toContain('resident');
    expect(resident.message).toContain('no migratory pattern to show');
    expect(resident.message).toContain('388 km');
    expect(resident.message).toContain('12 months');
  });

  it('says "insufficient data" with the record and month counts', () => {
    if (sparse.kind !== 'insufficient') throw new Error('expected insufficient');
    expect(sparse.message).toContain('Insufficient data');
    expect(sparse.message).toContain('28 records');
    expect(sparse.message).toContain('2 months');
    // It may mention residency to explain the ambiguity ("not enough to tell a
    // resident bird from a poorly-recorded migrant"), but it must never assert it.
    expect(sparse.message).not.toMatch(/\bis resident\b/);
    expect(sparse.message).not.toMatch(/no migratory pattern/);
  });

  it('distinguishes inconclusive from insufficient in words, not only in kind', () => {
    if (banded.kind !== 'inconclusive') throw new Error('expected inconclusive');
    expect(banded.message).toContain('inconclusive');
    expect(banded.message).toContain('473 km');
    // The distinguishing fact: there is plenty of data.
    expect(banded.message).toMatch(/plenty of it|3,600 records/);
    if (sparse.kind !== 'insufficient') throw new Error('expected insufficient');
    expect(banded.message).not.toBe(sparse.message);
  });

  it('never renders an empty map for a species with no analysis', () => {
    const o = migrationOutcome('Jerdon’s Courser', null);
    expect(o.kind).toBe('unknown-species');
    if (o.kind !== 'unknown-species') return;
    expect(o.message).toContain('not been analysed');
    expect(o.message).not.toContain('resident');
  });
});

describe('status labels and evidence', () => {
  it('labels each state distinctly', () => {
    const labels = [
      statusLabel(status()),
      statusLabel(status({ status: 'resident' })),
      statusLabel(status({ status: 'insufficient_data', insufficient_basis: 'coverage' })),
      statusLabel(status({ status: 'insufficient_data', insufficient_basis: 'inconclusive' })),
      statusLabel(null),
    ];
    expect(new Set(labels).size).toBe(5);
  });

  it('always carries the coverage behind a verdict', () => {
    const line = evidenceLine(status({ total_records: 3600, months_with_data: 12 }));
    expect(line).toContain('3,600 records');
    expect(line).toContain('12/12 months');
    expect(line).toContain('confidence');
  });

  it('says plainly when nothing was processed', () => {
    expect(evidenceLine(null)).toBe('no records processed');
  });
});

describe('telemetry', () => {
  beforeEach(() => telemetry.reset());

  const entry = (over: Partial<Parameters<typeof telemetry.record>[0]> = {}) => ({
    input: 'migration bar-tailed godwit',
    outcome: 'command' as const,
    verb: 'migration',
    llmCalled: false,
    networkCalled: true,
    parseMs: 0.05,
    totalMs: 12,
    ...over,
  });

  it('counts queries served without the agent', () => {
    telemetry.record(entry());
    telemetry.record(entry());
    telemetry.record(entry({ outcome: 'fallback', verb: null, llmCalled: true }));
    const s = telemetry.stats();
    expect(s.total).toBe(3);
    expect(s.withoutLLM).toBe(2);
    expect(s.withoutLLMPct).toBeCloseTo(2 / 3);
  });

  it('counts network separately from the agent', () => {
    // A local answer: help, or a disambiguation prompt.
    telemetry.record(entry({ outcome: 'disambiguate', networkCalled: false }));
    telemetry.record(entry()); // no agent, but did fetch data
    const s = telemetry.stats();
    expect(s.withoutLLM).toBe(2);
    expect(s.withoutNetwork).toBe(1);
  });

  it('breaks down by outcome and verb', () => {
    telemetry.record(entry());
    telemetry.record(entry({ verb: 'range' }));
    telemetry.record(entry({ outcome: 'fallback', verb: null, llmCalled: true }));
    const s = telemetry.stats();
    expect(s.byOutcome.command).toBe(2);
    expect(s.byOutcome.fallback).toBe(1);
    expect(s.byVerb.migration).toBe(1);
    expect(s.byVerb.range).toBe(1);
  });

  it('summarises without crashing on an empty history', () => {
    expect(telemetry.summary()).toBe('No queries yet.');
    telemetry.record(entry());
    expect(telemetry.summary()).toContain('100.0% answered without the agent');
  });
});
