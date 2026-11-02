/**
 * Local species resolution: free text to a canonical taxon id.
 *
 * No network, no model. MiniSearch narrows the ~17k-taxon alias table to a
 * handful of candidates; those are then re-scored with the deterministic
 * similarity in `./similarity`, because MiniSearch's own score is a relative
 * ranking signal, not a confidence — it shifts as the corpus changes, so a
 * threshold set against it would silently drift when the taxonomy is updated.
 *
 * The contract is deliberately three-valued. `resolved` means confident enough
 * to act on and display back; `ambiguous` means the user must choose;
 * `not_found` means nothing plausible. Nothing downstream may query data with
 * anything but the `TaxonId` these produce.
 */

import MiniSearch from 'minisearch';
import {
  CANDIDATE_FLOOR,
  CONFIDENCE_FLOOR,
  CONFIDENCE_MARGIN,
  MAX_CANDIDATES,
} from './config';
import { buildExactIndex } from './aliases';
import { compact, normalize } from './normalize';
import { prepare, similarityPrepared, type Prepared } from './similarity';
import type { AliasTable, Candidate, MatchKind, Resolution, Taxon, TaxonId } from './types';

/**
 * How many distinct taxa to re-score. Re-scoring is the expensive half, so this
 * is kept tight; retrieval is recall-oriented and already ranks the plausible
 * candidates first.
 */
const RETRIEVE = 24;

/**
 * One document per taxon, not per alias.
 *
 * Indexing each alias separately makes the corpus several times larger and
 * forces a dedupe pass over thousands of hits on every query; MiniSearch has to
 * score and sort all of them, which measured as the single largest cost in
 * resolve(). Concatenating a taxon's names into one field keeps identical
 * recall at a fraction of the work.
 */
interface IndexedTaxon {
  id: string;
  names: string;
}

export interface Resolver {
  resolve(query: string): Resolution;
  byId(id: string): Taxon | undefined;
  /** Validate that a string is a known canonical id. Returns undefined if not. */
  asTaxonId(value: string): TaxonId | undefined;
  size: number;
}

export function createResolver(table: AliasTable): Resolver {
  const taxaById = new Map<string, Taxon>(table.taxa.map(t => [t.taxonId, t]));
  const exact = buildExactIndex(table);

  // Aliases per taxon. Re-scoring compares against everything a taxon is known
  // by, not only the alias retrieval happened to hit.
  const aliasesByTaxon = new Map<string, string[]>();
  for (const entry of table.aliases) {
    const bucket = aliasesByTaxon.get(entry.taxonId);
    if (bucket) bucket.push(entry.alias);
    else aliasesByTaxon.set(entry.taxonId, [entry.alias]);
  }

  // Prepared forms are derived on first use and kept, not built up front:
  // a query scores a couple of dozen taxa, so eagerly preparing all ~73k
  // aliases cost about a second of startup to serve a few hundred of them.
  const preparedCache = new Map<string, Array<{ alias: string; prepared: Prepared }>>();
  function preparedAliases(taxonId: string): Array<{ alias: string; prepared: Prepared }> {
    let hit = preparedCache.get(taxonId);
    if (!hit) {
      // Deduped by compact form: "bar tailed godwit" and "bartailed godwit"
      // score identically, so scoring both is pure waste on the hot path.
      const byCompact = new Map<string, { alias: string; prepared: Prepared }>();
      for (const alias of aliasesByTaxon.get(taxonId) ?? []) {
        const prepared = prepare(alias);
        if (!byCompact.has(prepared.compact)) byCompact.set(prepared.compact, { alias, prepared });
      }
      hit = [...byCompact.values()];
      preparedCache.set(taxonId, hit);
    }
    return hit;
  }

  // Codes are exact by nature and already served by the O(1) map above, so they
  // are left out of the fuzzy corpus entirely.
  const namesByTaxon = new Map<string, string[]>();
  for (const entry of table.aliases) {
    if (entry.kind === 'code') continue;
    const bucket = namesByTaxon.get(entry.taxonId);
    if (bucket) bucket.push(entry.alias);
    else namesByTaxon.set(entry.taxonId, [entry.alias]);
  }

  const documents: IndexedTaxon[] = [...namesByTaxon].map(([id, names]) => ({
    id,
    names: [...new Set(names)].join(' '),
  }));

  // No `fuzzy` default. Per-search options MERGE over these rather than
  // replacing them, so a default of fuzzy:0.3 silently applies to every search
  // that does not explicitly turn it off — which made the cheap prefix-only
  // phase below quietly cost the same as the expensive one.
  const mini = new MiniSearch<IndexedTaxon>({
    fields: ['names'],
    storeFields: [],
    searchOptions: { prefix: true },
  });
  mini.addAll(documents);

  function candidateFor(taxonId: string, query: Prepared): Candidate | undefined {
    const taxon = taxaById.get(taxonId);
    if (!taxon) return undefined;
    let best = 0;
    let bestAlias = taxon.commonName;
    for (const { alias, prepared } of preparedAliases(taxonId)) {
      const score = similarityPrepared(query, prepared);
      if (score > best) {
        best = score;
        bestAlias = alias;
      }
      if (best === 1) break;
    }
    return { taxon, confidence: best, matchedAlias: bestAlias, matchKind: 'fuzzy' };
  }

  /**
   * Raw retrieval. `fuzzy` is optional because fuzzy term expansion over ~87k
   * aliases is by far the most expensive thing here.
   */
  function searchIds(
    query: string,
    fuzzy?: number,
    exclude?: string,
    forceOr = false,
  ): string[] {
    const multiToken = query.includes(' ') && !forceOr;
    // `fuzzy: false` is explicit, not merely omitted, for the reason above.
    const base = fuzzy ? { prefix: true, fuzzy } : { prefix: true, fuzzy: false as const };
    let results = mini.search(query, { ...base, combineWith: multiToken ? 'AND' : 'OR' });
    // Only widen to OR when AND found nothing at all. Re-running on a merely
    // small result set doubles the cost of the commonest shape of query — a
    // multi-word name, correctly spelled — for no added recall.
    if (results.length === 0 && multiToken) {
      results = mini.search(query, { ...base, combineWith: 'OR' });
    }
    const ids: string[] = [];
    for (const r of results) {
      if (r.id === exclude) continue;
      ids.push(r.id as string);
      if (ids.length >= RETRIEVE) break;
    }
    return ids;
  }

  function rank(ids: string[], query: Prepared): Candidate[] {
    return ids
      .map(id => candidateFor(id, query))
      .filter((c): c is Candidate => c !== undefined && c.confidence >= CANDIDATE_FLOOR)
      .sort(
        (a, b) =>
          b.confidence - a.confidence ||
          a.taxon.commonName.length - b.taxon.commonName.length ||
          a.taxon.commonName.localeCompare(b.taxon.commonName),
      );
  }

  /**
   * Two-phase retrieval: prefix-only first, fuzzy only when that failed to
   * produce a confident hit.
   *
   * Most queries are spelled correctly and are answered entirely by the cheap
   * phase; typos and contractions — the queries that actually need fuzzy — pay
   * for it. Recall is unchanged, because a cheap phase that does not clear the
   * auto-resolve floor always falls through to the full search.
   */
  function rankedCandidates(query: Prepared, exclude?: string): Candidate[] {
    const cheap = rank(searchIds(query.raw, undefined, exclude), query);
    if (cheap.length && cheap[0].confidence >= CONFIDENCE_FLOOR) return cheap;

    const seen = new Set<string>(cheap.map(c => c.taxon.taxonId));
    const extra = searchIds(query.raw, 0.3, exclude).filter(id => !seen.has(id));
    if (!extra.length) return cheap;
    return [...cheap, ...rank(extra, query)].sort(
      (a, b) =>
        b.confidence - a.confidence ||
        a.taxon.commonName.length - b.taxon.commonName.length ||
        a.taxon.commonName.localeCompare(b.taxon.commonName),
    );
  }

  /**
   * Candidates other than `excludeId`, ranked. Used to attach alternatives to
   * an exact hit: showing the resolved name back is only useful if the user can
   * act on it being wrong, and for look-alike pairs the runner-up is the whole
   * point.
   */
  /**
   * Look-alikes to offer beside a confident match, so a wrong auto-resolve is
   * correctable.
   *
   * Prefix-only and OR-combined: fuzzy expansion is pointless here (the query
   * already matched something exactly) and was measurably the most expensive
   * thing an exactly-spelled query did. OR rather than AND because the useful
   * alternatives are the taxa sharing a word — the other godwits — not the ones
   * matching every word.
   */
  function alternativesFor(query: Prepared, excludeId: string): Candidate[] {
    return rank(searchIds(query.raw, undefined, excludeId, true), query).slice(
      0,
      MAX_CANDIDATES - 1,
    );
  }

  function decide(query: string, ranked: Candidate[]): Resolution {
    const shown = ranked.filter(c => c.confidence >= CANDIDATE_FLOOR).slice(0, MAX_CANDIDATES);
    if (!shown.length) return { status: 'not_found', query, candidates: [] };

    const top = shown[0];
    const runnerUp = shown[1];
    const margin = runnerUp ? top.confidence - runnerUp.confidence : Infinity;

    // Both gates. The floor alone would resolve "godwit" to whichever godwit
    // happened to sort first; the margin is what makes that a question instead.
    if (top.confidence >= CONFIDENCE_FLOOR && margin >= CONFIDENCE_MARGIN) {
      return {
        status: 'resolved',
        taxon: top.taxon,
        confidence: top.confidence,
        matchedAlias: top.matchedAlias,
        matchKind: top.matchKind,
        alternatives: shown.slice(1),
      };
    }
    return { status: 'ambiguous', query, candidates: shown };
  }

  return {
    size: table.taxa.length,

    byId: (id: string) => taxaById.get(id),

    asTaxonId: (value: string) => (taxaById.has(value) ? (value as TaxonId) : undefined),

    resolve(rawQuery: string): Resolution {
      const query = normalize(rawQuery);
      if (!query) return { status: 'not_found', query: rawQuery, candidates: [] };
      const prepared = prepare(query);

      // 1. Exact alias hit. Still runs the ambiguity check: a four-letter
      //    banding code can be shared, and "Little Egret/Western Reef-Heron"
      //    style names put one string on two taxa.
      const hits = exact.get(query) ?? exact.get(compact(query)) ?? [];
      if (hits.length) {
        const unique = [...new Map(hits.map(h => [h.taxonId, h])).values()];
        if (unique.length === 1) {
          const taxon = taxaById.get(unique[0].taxonId);
          if (taxon) {
            return {
              status: 'resolved',
              taxon,
              confidence: 1,
              matchedAlias: unique[0].alias,
              matchKind: unique[0].kind,
              alternatives: alternativesFor(prepared, taxon.taxonId),
            };
          }
        } else if (unique.length > 1) {
          return {
            status: 'ambiguous',
            query: rawQuery,
            candidates: unique
              .map(h => {
                const taxon = taxaById.get(h.taxonId);
                return taxon
                  ? { taxon, confidence: 1, matchedAlias: h.alias, matchKind: h.kind }
                  : undefined;
              })
              .filter((c): c is Candidate => Boolean(c))
              .slice(0, MAX_CANDIDATES),
          };
        }
      }

      // 2. Retrieve, then re-score deterministically.
      return decide(rawQuery, rankedCandidates(prepared));
    },
  };
}

/**
 * Narrow a resolution to a canonical id, or throw.
 *
 * Call sites that query data take a `TaxonId`, so this is the only bridge from
 * user text to a query — an ambiguous or unfound resolution cannot cross it.
 */
export function requireTaxonId(resolution: Resolution): TaxonId {
  if (resolution.status !== 'resolved') {
    throw new Error(
      `Refusing to query with an unresolved species (${resolution.status}). ` +
        'Present the candidates and let the user choose.',
    );
  }
  return resolution.taxon.taxonId;
}
