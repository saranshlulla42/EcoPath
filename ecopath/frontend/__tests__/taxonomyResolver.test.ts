import { beforeAll, describe, expect, it } from 'vitest';
import { buildAliasTable } from '../lib/taxonomy/aliases';
import { CONFIDENCE_FLOOR, CONFIDENCE_MARGIN } from '../lib/taxonomy/config';
import { createResolver, requireTaxonId, type Resolver } from '../lib/taxonomy/resolver';
import { similarity } from '../lib/taxonomy/similarity';
import { CATALOGUE_SCI_NAMES, TAXONOMY_FIXTURE } from './fixtures/taxonomy.fixture';

let resolver: Resolver;

beforeAll(() => {
  resolver = createResolver(
    buildAliasTable(TAXONOMY_FIXTURE, { catalogueSciNames: CATALOGUE_SCI_NAMES }),
  );
});

/** Ids of the candidates offered, in rank order. */
function candidateIds(query: string): string[] {
  const r = resolver.resolve(query);
  if (r.status === 'resolved') return [r.taxon.taxonId, ...r.alternatives.map(c => c.taxon.taxonId)];
  if (r.status === 'ambiguous') return r.candidates.map(c => c.taxon.taxonId);
  return [];
}

describe('godwit near-miss — the case a wrong guess must never be made on', () => {
  it('refuses to pick a godwit from the bare family name', () => {
    const r = resolver.resolve('godwit');
    expect(r.status).toBe('ambiguous');
    if (r.status !== 'ambiguous') return;
    const ids = r.candidates.map(c => c.taxon.taxonId);
    expect(ids).toContain('bartgo');
    expect(ids).toContain('bktgod');
  });

  it('scores both tailed godwits identically for "godwit", so no margin exists', () => {
    const bar = similarity('godwit', 'bar-tailed godwit');
    const black = similarity('godwit', 'black-tailed godwit');
    expect(Math.abs(bar - black)).toBeLessThan(CONFIDENCE_MARGIN);
  });

  it('resolves each godwit exactly when fully named', () => {
    for (const [query, id] of [
      ['Bar-tailed Godwit', 'bartgo'],
      ['Black-tailed Godwit', 'bktgod'],
      ['bartailed godwit', 'bartgo'],
      ['blacktailed godwit', 'bktgod'],
      ['Limosa lapponica', 'bartgo'],
      ['Limosa limosa', 'bktgod'],
    ] as const) {
      const r = resolver.resolve(query);
      expect(r.status, `${query} should resolve`).toBe('resolved');
      if (r.status === 'resolved') expect(r.taxon.taxonId, `${query}`).toBe(id);
    }
  });

  it('resolves a typo to the right godwit, not its look-alike', () => {
    const r = resolver.resolve('blak-tailed godwit');
    expect(r.status).toBe('resolved');
    if (r.status !== 'resolved') return;
    expect(r.taxon.taxonId).toBe('bktgod');
    expect(r.taxon.commonName).toBe('Black-tailed Godwit');
  });

  it('stays ambiguous when the modifier is truncated to a shared prefix', () => {
    // "b-tailed" is equally close to Bar- and Black-; guessing here is the exact
    // failure the margin gate exists to prevent.
    const r = resolver.resolve('b-tailed godwit');
    expect(r.status).toBe('ambiguous');
    if (r.status !== 'ambiguous') return;
    expect(r.candidates.map(c => c.taxon.taxonId)).toEqual(
      expect.arrayContaining(['bartgo', 'bktgod']),
    );
  });

  it('does not let a shared banding code auto-resolve to one of them', () => {
    // BTGO is carried by both Bar-tailed and Black-tailed in the fixture.
    const r = resolver.resolve('BTGO');
    expect(r.status).toBe('ambiguous');
    if (r.status !== 'ambiguous') return;
    expect(r.candidates.map(c => c.taxon.taxonId).sort()).toEqual(['bartgo', 'bktgod']);
  });

  it('never surfaces a godwit for an unrelated query', () => {
    expect(candidateIds('house sparrow')).not.toContain('bartgo');
  });
});

describe('typos and contractions', () => {
  it('resolves "arcter" to Arctic Tern over Arctic Warbler', () => {
    const r = resolver.resolve('arcter');
    expect(r.status).toBe('resolved');
    if (r.status !== 'resolved') return;
    expect(r.taxon.commonName).toBe('Arctic Tern');
  });

  it('resolves "arcter" on similarity alone, not just because it is the species code', () => {
    // Strip every code alias so only name similarity can carry the match.
    const namesOnly = createResolver({
      taxa: buildAliasTable(TAXONOMY_FIXTURE).taxa,
      aliases: buildAliasTable(TAXONOMY_FIXTURE).aliases.filter(a => a.kind !== 'code'),
    });
    const r = namesOnly.resolve('arcter');
    expect(r.status).toBe('resolved');
    if (r.status !== 'resolved') return;
    expect(r.taxon.commonName).toBe('Arctic Tern');
    expect(r.confidence).toBeGreaterThanOrEqual(CONFIDENCE_FLOOR);
    expect(similarity('arcter', 'Arctic Tern')).toBeGreaterThan(
      similarity('arcter', 'Arctic Warbler'),
    );
  });

  it('handles ordinary misspellings', () => {
    for (const [query, name] of [
      ['hous sparow', 'House Sparrow'],
      ['arctic tren', 'Arctic Tern'],
      ['saurs crane', 'Sarus Crane'],
    ] as const) {
      const r = resolver.resolve(query);
      expect(r.status, `${query} should resolve`).toBe('resolved');
      if (r.status === 'resolved') expect(r.taxon.commonName, query).toBe(name);
    }
  });

  it('accepts British spelling for a name catalogued the American way', () => {
    const r = resolver.resolve('Grey Heron');
    expect(r.status).toBe('resolved');
    if (r.status === 'resolved') expect(r.taxon.taxonId).toBe('greher1');
  });
});

describe('substring decoys — what the current resolver gets wrong', () => {
  it('does not resolve "tern" to anything, because several terns match', () => {
    const r = resolver.resolve('tern');
    expect(r.status).toBe('ambiguous');
  });

  it('ranks real terns above species that merely contain the letters', () => {
    const ids = candidateIds('tern');
    const worstTern = Math.max(ids.indexOf('arcter'), ids.indexOf('whiter2'), ids.indexOf('caster1'));
    const decoys = [ids.indexOf('rerswa1'), ids.indexOf('eaywag')].filter(i => i >= 0);
    for (const decoy of decoys) expect(decoy).toBeGreaterThan(worstTern);
  });

  it('scores a mid-word "tern" below the auto-resolve floor', () => {
    expect(similarity('tern', 'Eastern Red-rumped Swallow')).toBeLessThan(CONFIDENCE_FLOOR);
    expect(similarity('tern', 'Whiskered Tern')).toBeGreaterThanOrEqual(CONFIDENCE_FLOOR);
  });
});

describe('codes and alternate forms', () => {
  it('resolves a six-letter species code', () => {
    const r = resolver.resolve('houspa');
    expect(r.status).toBe('resolved');
    if (r.status !== 'resolved') return;
    expect(r.taxon.commonName).toBe('House Sparrow');
    expect(r.matchKind).toBe('code');
  });

  it('resolves an unambiguous four-letter banding code', () => {
    const r = resolver.resolve('HOSP');
    expect(r.status).toBe('resolved');
    if (r.status === 'resolved') expect(r.taxon.taxonId).toBe('houspa');
  });

  it('resolves an abbreviated scientific name', () => {
    const r = resolver.resolve('L. limosa');
    expect(r.status).toBe('resolved');
    if (r.status === 'resolved') expect(r.taxon.taxonId).toBe('bktgod');
  });

  it('folds a subspecies onto its parent species rather than making it a target', () => {
    const r = resolver.resolve('House Sparrow (Indian)');
    expect(r.status).toBe('resolved');
    if (r.status !== 'resolved') return;
    expect(r.taxon.taxonId).toBe('houspa');
    expect(r.taxon.category).toBe('species');
    expect(resolver.byId('houspa2')).toBeUndefined();
  });

  it('is insensitive to case, punctuation and spacing', () => {
    for (const q of ['BAR-TAILED GODWIT', '  bar tailed  godwit ', 'Bar–tailed Godwit']) {
      const r = resolver.resolve(q);
      expect(r.status, q).toBe('resolved');
      if (r.status === 'resolved') expect(r.taxon.taxonId, q).toBe('bartgo');
    }
  });
});

describe('resolution contract', () => {
  it('returns ranked candidates with scores, never a bare guess', () => {
    const r = resolver.resolve('godwit');
    expect(r.status).toBe('ambiguous');
    if (r.status !== 'ambiguous') return;
    expect(r.candidates.length).toBeGreaterThan(1);
    for (const c of r.candidates) {
      expect(c.confidence).toBeGreaterThan(0);
      expect(c.confidence).toBeLessThanOrEqual(1);
      expect(c.matchedAlias).toBeTruthy();
    }
    const scores = r.candidates.map(c => c.confidence);
    expect(scores).toEqual([...scores].sort((a, b) => b - a));
  });

  it('carries the matched alias so the resolved name can be shown back', () => {
    const r = resolver.resolve('blak-tailed godwit');
    if (r.status !== 'resolved') throw new Error('expected resolved');
    expect(r.matchedAlias).toContain('godwit');
    expect(r.taxon.commonName).toBe('Black-tailed Godwit');
  });

  it('offers alternatives even when confident, so a wrong auto-resolve is correctable', () => {
    const r = resolver.resolve('blacktailed godwit');
    if (r.status !== 'resolved') throw new Error('expected resolved');
    expect(r.alternatives.length).toBeGreaterThan(0);
  });

  it('reports not_found for input that matches nothing', () => {
    for (const q of ['zzzzqqqq', '', '   ']) {
      expect(resolver.resolve(q).status).toBe('not_found');
    }
  });

  it('distinguishes "known taxon" from "EcoPath has data"', () => {
    const arctic = resolver.resolve('Arctic Tern');
    if (arctic.status !== 'resolved') throw new Error('expected resolved');
    // Resolution succeeds; the catalogue simply does not hold it. Collapsing
    // these two into "not found" is the thing the domain rules forbid.
    expect(arctic.taxon.inCatalogue).toBe(false);

    const sparrow = resolver.resolve('House Sparrow');
    if (sparrow.status !== 'resolved') throw new Error('expected resolved');
    expect(sparrow.taxon.inCatalogue).toBe(true);
  });
});

describe('canonical id is the only way into a data query', () => {
  it('throws rather than letting an ambiguous match through', () => {
    expect(() => requireTaxonId(resolver.resolve('godwit'))).toThrow(/unresolved/i);
    expect(() => requireTaxonId(resolver.resolve('zzzzqqqq'))).toThrow(/unresolved/i);
  });

  it('yields the canonical id for a confident match', () => {
    expect(requireTaxonId(resolver.resolve('Bar-tailed Godwit'))).toBe('bartgo');
  });

  it('rejects a string that is not a known taxon id', () => {
    expect(resolver.asTaxonId('bartgo')).toBe('bartgo');
    expect(resolver.asTaxonId('Bar-tailed Godwit')).toBeUndefined();
    expect(resolver.asTaxonId('nonsense')).toBeUndefined();
  });
});

describe('performance', () => {
  it('resolves in well under a millisecond per query', () => {
    const queries = ['godwit', 'arcter', 'hous sparow', 'tern', 'Limosa limosa', 'HOSP'];
    // Warm the index and JIT before timing.
    for (let i = 0; i < 200; i++) resolver.resolve(queries[i % queries.length]);

    const runs = 2000;
    const started = performance.now();
    for (let i = 0; i < runs; i++) resolver.resolve(queries[i % queries.length]);
    const perQuery = (performance.now() - started) / runs;

    expect(perQuery).toBeLessThan(1);
  });
});
