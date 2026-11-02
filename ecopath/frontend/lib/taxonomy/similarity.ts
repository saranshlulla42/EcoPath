/**
 * Similarity scoring for species names, in [0, 1].
 *
 * Two signals, because command-bar input fails in two different ways:
 *
 *   - *Typos* ("blak-tailed godwit") — handled by Jaro-Winkler, which is
 *     forgiving of substitutions and transpositions and rewards a shared
 *     prefix.
 *   - *Contractions* ("arcter" for Arctic Tern) — handled by a subsequence
 *     scorer in the style of a fuzzy file finder: every query character must
 *     appear in order, and characters that begin a word or continue a run
 *     score full marks.
 *
 * The final score is the better of the two, so neither failure mode is
 * penalised for not looking like the other.
 *
 * Everything works on `Prepared` values. Normalising a name costs more than
 * scoring it, and aliases are normalised once when the table is built, so
 * re-deriving them per comparison would dominate the runtime — which it did,
 * measurably, before this split.
 */

import { compact, normalize, tokenStartFlags, tokens } from './normalize';

/** Weight for a matched character that neither starts a word nor continues a run. */
const LOOSE_MATCH = 0.5;

/** A name with its derived forms computed once. */
export interface Prepared {
  /** Normalised, space-separated. */
  raw: string;
  /** Normalised with separators removed. */
  compact: string;
  /** Per character of `compact`, whether it begins a token. */
  starts: boolean[];
  tokens: string[];
}

export function prepare(name: string): Prepared {
  const raw = normalize(name);
  return {
    raw,
    compact: raw.replace(/ /g, ''),
    starts: tokenStartFlags(raw),
    tokens: raw ? raw.split(' ') : [],
  };
}

export function jaro(a: string, b: string): number {
  if (a === b) return 1;
  if (!a.length || !b.length) return 0;

  const window = Math.max(0, Math.floor(Math.max(a.length, b.length) / 2) - 1);
  const aMatched = new Array<boolean>(a.length).fill(false);
  const bMatched = new Array<boolean>(b.length).fill(false);

  let matches = 0;
  for (let i = 0; i < a.length; i++) {
    const start = Math.max(0, i - window);
    const end = Math.min(i + window + 1, b.length);
    for (let j = start; j < end; j++) {
      if (bMatched[j] || a[i] !== b[j]) continue;
      aMatched[i] = true;
      bMatched[j] = true;
      matches++;
      break;
    }
  }
  if (!matches) return 0;

  let transpositions = 0;
  let k = 0;
  for (let i = 0; i < a.length; i++) {
    if (!aMatched[i]) continue;
    while (!bMatched[k]) k++;
    if (a[i] !== b[k]) transpositions++;
    k++;
  }

  return (matches / a.length + matches / b.length + (matches - transpositions / 2) / matches) / 3;
}

/** Jaro-Winkler: Jaro with a bonus for a shared prefix of up to 4 characters. */
export function jaroWinkler(a: string, b: string, scale = 0.1): number {
  const base = jaro(a, b);
  let prefix = 0;
  while (prefix < Math.min(4, a.length, b.length) && a[prefix] === b[prefix]) prefix++;
  return base + prefix * scale * (1 - base);
}

/**
 * Fuzzy-finder style score: can every character of the query be found in the
 * name in order, and how well-placed are those characters?
 *
 * Matching is optimal, not greedy left-to-right. That distinction decides real
 * cases: for "arcter", a greedy matcher takes the `t` inside "Arctic" and then
 * limps to the `e` in "Tern", scoring Arctic Tern no better than Arctic
 * Warbler. The optimal path takes `t` at the start of "Tern" instead and scores
 * a perfect run — the difference between resolving the query and putting two
 * unrelated birds in front of the user as equals.
 *
 * Returns 0 when the query is not a subsequence at all.
 */
export function subsequenceScorePrepared(q: Prepared, n: Prepared): number {
  const query = q.compact;
  const name = n.compact;
  if (!query || !name || query.length > name.length) return 0;

  const starts = n.starts;
  const NEG = -Infinity;

  // best[j] = best score for the query prefix matched so far, with its last
  // character placed at name position j.
  let best = new Array<number>(name.length).fill(NEG);
  for (let j = 0; j < name.length; j++) {
    if (name[j] === query[0]) best[j] = starts[j] ? 1 : LOOSE_MATCH;
  }

  for (let i = 1; i < query.length; i++) {
    const next = new Array<number>(name.length).fill(NEG);
    // Running maximum over placements that leave a gap before position j.
    let gapMax = NEG;
    let any = false;
    for (let j = 1; j < name.length; j++) {
      if (j >= 2 && best[j - 2] > gapMax) gapMax = best[j - 2];
      if (name[j] !== query[i]) continue;
      const consecutive = best[j - 1] > NEG ? best[j - 1] + 1 : NEG;
      const jumped = gapMax > NEG ? gapMax + (starts[j] ? 1 : LOOSE_MATCH) : NEG;
      const score = Math.max(consecutive, jumped);
      next[j] = score;
      if (score > NEG) any = true;
    }
    if (!any) return 0;
    best = next;
  }

  let top = NEG;
  for (const v of best) if (v > top) top = v;
  return top === NEG ? 0 : top / query.length;
}

/**
 * Token-set similarity: each query token scored against its best name token.
 *
 * Lets "godwit bar-tailed" match "Bar-tailed Godwit" despite the reordering,
 * which plain string distance would punish heavily.
 */
export function tokenSetScorePrepared(q: Prepared, n: Prepared): number {
  const qt = q.tokens;
  const nt = n.tokens;
  if (!qt.length || !nt.length) return 0;
  let total = 0;
  let worst = 1;
  for (const a of qt) {
    let best = 0;
    for (const b of nt) {
      const s = jaroWinkler(a, b);
      if (s > best) best = s;
      if (best === 1) break;
    }
    total += best;
    if (best < worst) worst = best;
  }
  const mean = total / qt.length;
  // The mean alone lets a shared group noun carry a bad match on the token that
  // actually distinguishes the species: "perigrine falcon" scores nearly as
  // well against Prairie Falcon as against Peregrine, because "falcon" matches
  // both perfectly. Weighting by the worst-matched query token asks that every
  // part of the query be accounted for, which is what separates a typo from a
  // different bird.
  const weakestLink = 0.7 + 0.3 * worst;
  // Unmatched name tokens dilute the score, so "godwit" alone cannot look like
  // a full match for "Bar-tailed Godwit" on this signal.
  const coverage = Math.min(qt.length, nt.length) / Math.max(qt.length, nt.length);
  return mean * weakestLink * (0.6 + 0.4 * coverage);
}

/** Best available evidence that the query denotes the name. */
export function similarityPrepared(q: Prepared, n: Prepared): number {
  if (!q.raw || !n.raw) return 0;
  if (q.raw === n.raw || q.compact === n.compact) return 1;

  // Cheapest discriminating signal first; each can reach 1.0, so an early exit
  // is exact rather than an approximation.
  const sub = subsequenceScorePrepared(q, n);
  if (sub === 1) return 1;
  const jw = jaroWinkler(q.raw, n.raw);
  if (jw === 1) return 1;
  const best = sub > jw ? sub : jw;
  const tokenSet = tokenSetScorePrepared(q, n);
  return tokenSet > best ? tokenSet : best;
}

/** Convenience wrapper for callers that hold raw strings. */
export function similarity(query: string, name: string): number {
  return similarityPrepared(prepare(query), prepare(name));
}

// Raw-string variants, kept for tests and ad-hoc use.
export function subsequenceScore(query: string, name: string): number {
  return subsequenceScorePrepared(prepare(query), prepare(name));
}

export function tokenSetScore(query: string, name: string): number {
  return tokenSetScorePrepared(prepare(query), prepare(name));
}

export { compact, normalize, tokens };
