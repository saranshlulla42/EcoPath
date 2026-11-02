import { beforeAll, describe, expect, it } from 'vitest';
import { buildAliasTable } from '../lib/taxonomy/aliases';
import { createResolver, type Resolver } from '../lib/taxonomy/resolver';
import { parse, type ParseOptions } from '../lib/commands/parse';
import { COMMANDS, BY_VERB } from '../lib/commands/registry';
import { TAXONOMY_FIXTURE } from './fixtures/taxonomy.fixture';

let resolver: Resolver;
let opts: ParseOptions;

const REGIONS = new Set(['gujarat', 'kerala', 'assam', 'tamil nadu']);

beforeAll(() => {
  resolver = createResolver(buildAliasTable(TAXONOMY_FIXTURE));
  opts = { resolver, regions: REGIONS };
});

describe('registry', () => {
  it('has no colliding verbs or aliases', () => {
    const keys = COMMANDS.flatMap(c => [c.verb, ...c.aliases]);
    expect(new Set(keys).size).toBe(keys.length);
    expect(BY_VERB.size).toBe(keys.length);
  });

  it('every command documents itself', () => {
    for (const c of COMMANDS) {
      expect(c.summary, c.verb).toBeTruthy();
      expect(c.example, c.verb).toBeTruthy();
      for (const a of c.args) expect(a.description, `${c.verb}.${a.name}`).toBeTruthy();
    }
  });
});

describe('deterministic parsing — the model must not be reached', () => {
  it('parses verb plus species without any fallback', () => {
    const r = parse('migration bar-tailed godwit', opts);
    expect(r.kind).toBe('command');
    if (r.kind !== 'command') return;
    expect(r.spec.verb).toBe('migration');
    expect(r.species[0].taxon.taxonId).toBe('bartgo');
  });

  it('accepts aliases for the verb', () => {
    for (const [input, verb] of [
      ['migrate arctic tern', 'migration'],
      ['map arctic tern', 'range'],
      ['trend house sparrow', 'chart'],
      ['info house sparrow', 'species'],
    ] as const) {
      const r = parse(input, opts);
      expect(r.kind, input).toBe('command');
      if (r.kind === 'command') expect(r.spec.verb, input).toBe(verb);
    }
  });

  it('treats a bare species name as a profile lookup', () => {
    const r = parse('Bar-tailed Godwit', opts);
    expect(r.kind).toBe('command');
    if (r.kind !== 'command') return;
    expect(r.spec.verb).toBe('species');
    expect(r.species[0].taxon.taxonId).toBe('bartgo');
  });

  it('resolves a misspelled species without help from the agent', () => {
    const r = parse('migration blak-tailed godwit', opts);
    expect(r.kind).toBe('command');
    if (r.kind === 'command') expect(r.species[0].taxon.taxonId).toBe('bktgod');
  });

  it('finds the verb behind a polite preamble', () => {
    for (const input of [
      'show me the migration of the arctic tern',
      'the migration of the arctic tern',
      'migration of the arctic tern',
    ]) {
      const r = parse(input, opts);
      expect(r.kind, input).toBe('command');
      if (r.kind === 'command') {
        expect(r.spec.verb, input).toBe('migration');
        expect(r.species[0].taxon.commonName, input).toBe('Arctic Tern');
      }
    }
  });

  it('does not let a verb word deep in a sentence hijack the parse', () => {
    // "range" appears, but only after real words, so this is a sentence.
    const r = parse('what determines the range of a godwit population', opts);
    expect(r.kind).toBe('fallback');
  });

  it('pulls a trailing month off a range command', () => {
    for (const input of ['range arctic tern january', 'range arctic tern 1']) {
      const r = parse(input, opts);
      expect(r.kind, input).toBe('command');
      if (r.kind === 'command') {
        expect(r.values.month, input).toBe(1);
        expect(r.species[0].taxon.commonName, input).toBe('Arctic Tern');
      }
    }
  });

  it('does not mistake part of a species name for a month', () => {
    // "May" would be a month, but here the species phrase must survive intact.
    const r = parse('range house sparrow', opts);
    expect(r.kind).toBe('command');
    if (r.kind === 'command') {
      expect(r.values.month).toBeUndefined();
      expect(r.species[0].taxon.commonName).toBe('House Sparrow');
    }
  });

  it('pulls a trailing metric off a chart command', () => {
    const r = parse('chart house sparrow anomalies', opts);
    expect(r.kind).toBe('command');
    if (r.kind === 'command') {
      expect(r.values.metric).toBe('anomalies');
      expect(r.species[0].taxon.commonName).toBe('House Sparrow');
    }
  });

  it('splits two-species commands on and / vs', () => {
    for (const input of [
      'compare bar-tailed godwit and black-tailed godwit',
      'compare bar-tailed godwit vs black-tailed godwit',
    ]) {
      const r = parse(input, opts);
      expect(r.kind, input).toBe('command');
      if (r.kind === 'command') {
        expect(r.species.map(s => s.taxon.taxonId)).toEqual(['bartgo', 'bktgod']);
      }
    }
  });

  it('parses a region argument', () => {
    const r = parse('weather house sparrow gujarat', opts);
    expect(r.kind).toBe('command');
    if (r.kind === 'command') {
      expect(r.spec.verb).toBe('weather');
      expect(r.values.region).toBe('gujarat');
      expect(r.species[0].taxon.commonName).toBe('House Sparrow');
    }

    const r2 = parse('region kerala', opts);
    expect(r2.kind).toBe('command');
    if (r2.kind === 'command') expect(r2.values.region).toBe('kerala');
  });

  it('parses commands that take no arguments', () => {
    const r = parse('dataset', opts);
    expect(r.kind).toBe('command');
    if (r.kind === 'command') expect(r.spec.verb).toBe('dataset');
  });
});

describe('ambiguity is answered locally, not by the agent', () => {
  it('offers candidates rather than guessing a godwit', () => {
    const r = parse('migration godwit', opts);
    expect(r.kind).toBe('disambiguate');
    if (r.kind !== 'disambiguate') return;
    expect(r.spec?.verb).toBe('migration');
    const ids = r.resolution.candidates.map(c => c.taxon.taxonId);
    expect(ids).toContain('bartgo');
    expect(ids).toContain('bktgod');
  });

  it('offers candidates for a bare ambiguous name too', () => {
    const r = parse('godwit', opts);
    expect(r.kind).toBe('disambiguate');
  });

  it('never returns a command when the species was ambiguous', () => {
    for (const input of ['godwit', 'migration godwit', 'chart godwit', 'range godwit']) {
      expect(parse(input, opts).kind, input).not.toBe('command');
    }
  });
});

describe('fallback is reserved for genuinely open questions', () => {
  it('sends an open-ended question to the agent', () => {
    const r = parse('why do godwits fly nonstop over the Pacific?', opts);
    expect(r.kind).toBe('fallback');
    if (r.kind === 'fallback') expect(r.reason).toBe('unknown-intent');
  });

  it('honours an explicit ask', () => {
    const r = parse('ask what drives altitudinal migration in the Himalaya', opts);
    expect(r.kind).toBe('fallback');
    if (r.kind !== 'fallback') return;
    expect(r.reason).toBe('explicit');
    expect(r.text).toBe('what drives altitudinal migration in the Himalaya');
  });

  it('marks a known verb with an unresolvable species distinctly', () => {
    const r = parse('migration zzzzqqqq', opts);
    expect(r.kind).toBe('fallback');
    if (r.kind === 'fallback') expect(r.reason).toBe('unresolved-species');
  });

  it('returns empty for blank input rather than calling anything', () => {
    for (const input of ['', '   ']) expect(parse(input, opts).kind).toBe('empty');
  });
});

describe('commands whose backing is missing still avoid the agent', () => {
  it('flags unavailable rather than falling back', () => {
    for (const input of ['top threatened', 'dataset']) {
      const r = parse(input, opts);
      expect(r.kind, input).toBe('command');
      if (r.kind === 'command') expect(r.unavailable, input).toBeTruthy();
    }
  });
});

describe('parse cost', () => {
  it('parses in well under a millisecond', () => {
    const inputs = [
      'migration bar-tailed godwit',
      'godwit',
      'chart house sparrow anomalies',
      'range arctic tern january',
      'why do godwits fly nonstop over the Pacific?',
      'Bar-tailed Godwit',
    ];
    for (let i = 0; i < 200; i++) parse(inputs[i % inputs.length], opts);

    const batches: number[] = [];
    for (let b = 0; b < 5; b++) {
      const runs = 400;
      const started = performance.now();
      for (let i = 0; i < runs; i++) parse(inputs[i % inputs.length], opts);
      batches.push((performance.now() - started) / runs);
    }
    const best = Math.min(...batches);
    console.log(`  parse: ${best.toFixed(3)} ms/query`);
    expect(best).toBeLessThan(1);
  });
});
