/**
 * Deterministic parsing. The model is the last resort, not the first.
 *
 * The order matters and is the whole architecture: match a verb, resolve the
 * entity locally through the Stage 3 index, and only if one of those fails does
 * anything leave the machine. A confidently-parsed command never calls the
 * agent, so the common case — a researcher asking where a bird is — costs
 * nothing and answers in under a millisecond.
 *
 * An ambiguous species is NOT a reason to call the model. Stage 3 already
 * produced ranked candidates; asking which one is a better answer than letting
 * a language model guess, and it is the rule that fuzzy matches never reach a
 * data query without a canonical id.
 */

import type { Resolution, Taxon } from '../taxonomy/types';
import type { Resolver } from '../taxonomy/resolver';
import { lookup, type ArgSpec, type CommandSpec } from './registry';
import { matchIntent, stripScaffolding } from './intents';

export interface ResolvedSpecies {
  taxon: Taxon;
  /** The text the user typed for this argument, for echoing back. */
  input: string;
  confidence: number;
  matchedAlias: string;
}

export type ParseResult =
  | {
      kind: 'command';
      spec: CommandSpec;
      /** Species arguments, already resolved to canonical taxa. */
      species: ResolvedSpecies[];
      /** Scalar arguments: month, metric, region, iucn, text. */
      values: Record<string, string | number>;
      /** True when the command is known but its backing is not available yet. */
      unavailable?: string;
    }
  | {
      kind: 'disambiguate';
      spec: CommandSpec | null;
      argName: string;
      input: string;
      resolution: Extract<Resolution, { status: 'ambiguous' }>;
    }
  | { kind: 'fallback'; reason: FallbackReason; text: string }
  | { kind: 'empty' };

export type FallbackReason =
  /** No verb matched and the whole input is not a species. */
  | 'unknown-intent'
  /** A verb matched but a required species argument resolved to nothing. */
  | 'unresolved-species'
  /** The user explicitly asked the agent. */
  | 'explicit';

const MONTHS: Record<string, number> = {
  january: 1, february: 2, march: 3, april: 4, may: 5, june: 6,
  july: 7, august: 8, september: 9, october: 10, november: 11, december: 12,
  jan: 1, feb: 2, mar: 3, apr: 4, jun: 6, jul: 7, aug: 8,
  sep: 9, sept: 9, oct: 10, nov: 11, dec: 12,
};

/** Filler words that carry no meaning for the parser. */
const NOISE = new Set(['the', 'a', 'an', 'of', 'for', 'in', 'on', 'me', 'show', 'please']);

/**
 * Words that open a question. Only consulted when no verb matched, so aliases
 * that happen to be question words ("where" for `range`) are unaffected.
 */
const QUESTION_WORDS = new Set([
  'why', 'what', 'how', 'when', 'which', 'who', 'whom', 'whose',
  'do', 'does', 'did', 'is', 'are', 'was', 'were', 'can', 'could',
  'should', 'would', 'will', 'tell',
]);

/**
 * Longest a bare species name may plausibly be. The longest real eBird common
 * names run to four words; six leaves room without letting a sentence through.
 */
const MAX_SPECIES_TOKENS = 6;

/**
 * Whether input with no verb is a question rather than a name.
 *
 * Without this, "why do godwits fly nonstop over the Pacific?" gets handed to
 * the species resolver, matches "godwit" ambiguously, and the user is asked to
 * pick a godwit instead of getting an answer — a fallback misrouted as a
 * disambiguation.
 */
function looksLikeQuestion(raw: string, tokens: string[]): boolean {
  return raw.includes('?') || QUESTION_WORDS.has(tokens[0].toLowerCase());
}

/** Splits `compare X and Y` / `X vs Y` into two halves. */
const PAIR_SEPARATOR = /\s+(?:and|vs\.?|versus|against)\s+/i;

export interface ParseOptions {
  resolver: Resolver;
  /** Known Indian state names/codes, lowercased. Optional. */
  regions?: Set<string>;
}

function parseMonth(token: string): number | null {
  const named = MONTHS[token.toLowerCase()];
  if (named) return named;
  const n = Number(token);
  return Number.isInteger(n) && n >= 1 && n <= 12 ? n : null;
}

/** How far into the input a verb may hide behind filler. */
const MAX_PREAMBLE = 3;

/**
 * Locate the command verb, allowing a short polite preamble.
 *
 * People type "show me the migration of X" as readily as "migration X", and
 * treating the first word as authoritative sends the whole phrase to the
 * species resolver, where it becomes an ambiguous mess. The scan is bounded to
 * a few tokens so a verb word occurring inside a long species name cannot
 * hijack the parse.
 */
function findVerb(tokens: string[]): { spec: CommandSpec | undefined; verbIndex: number } {
  const direct = lookup(tokens[0]);
  if (direct) return { spec: direct, verbIndex: 0 };

  const limit = Math.min(tokens.length, MAX_PREAMBLE + 1);
  for (let i = 1; i < limit; i++) {
    // Everything skipped must be filler; a real word before the verb means the
    // input is a sentence, not a command.
    if (!NOISE.has(tokens[i - 1].toLowerCase())) break;
    const spec = lookup(tokens[i]);
    if (spec) return { spec, verbIndex: i };
  }
  return { spec: undefined, verbIndex: 0 };
}


function stripNoise(tokens: string[]): string[] {
  const kept = tokens.filter(t => !NOISE.has(t.toLowerCase()));
  // Never strip everything: "in" alone is a region verb.
  return kept.length ? kept : tokens;
}

/**
 * Pull trailing scalar arguments (month, metric, iucn, region) off the tail,
 * leaving the rest as the species phrase.
 *
 * Working from the end matters: species names are multi-word and unbounded,
 * while these values are single tokens from closed sets, so the tail is the
 * only place they can be identified without guessing where the name stops.
 */
function extractTrailingValues(
  tokens: string[],
  argSpecs: ArgSpec[],
  regions?: Set<string>,
): { values: Record<string, string | number>; rest: string[] } {
  const values: Record<string, string | number> = {};
  const rest = [...tokens];

  const wants = (type: ArgSpec['type']) => argSpecs.find(a => a.type === type && !(a.name in values));

  // Repeat: a command may take several scalars ("range X january", "list CR kerala").
  for (let guard = 0; guard < argSpecs.length + 1 && rest.length; guard++) {
    const tail = rest[rest.length - 1];
    const lower = tail.toLowerCase();

    const monthArg = wants('month');
    if (monthArg) {
      const m = parseMonth(tail);
      if (m !== null) {
        values[monthArg.name] = m;
        rest.pop();
        continue;
      }
    }

    const metricArg = wants('metric');
    if (metricArg?.values?.includes(lower)) {
      values[metricArg.name] = lower;
      rest.pop();
      continue;
    }

    const iucnArg = wants('iucn');
    if (iucnArg?.values?.some(v => v.toLowerCase() === lower)) {
      values[iucnArg.name] = tail.toUpperCase();
      rest.pop();
      continue;
    }

    const regionArg = wants('region');
    if (regionArg && regions?.has(lower)) {
      values[regionArg.name] = tail;
      rest.pop();
      continue;
    }

    break;
  }

  return { values, rest };
}

function resolveSpeciesArg(
  phrase: string,
  resolver: Resolver,
): { ok: true; value: ResolvedSpecies } | { ok: false; resolution: Resolution } {
  const resolution = resolver.resolve(phrase);
  if (resolution.status === 'resolved') {
    return {
      ok: true,
      value: {
        taxon: resolution.taxon,
        input: phrase,
        confidence: resolution.confidence,
        matchedAlias: resolution.matchedAlias,
      },
    };
  }
  return { ok: false, resolution };
}

export function parse(input: string, options: ParseOptions): ParseResult {
  const raw = (input ?? '').trim();
  if (!raw) return { kind: 'empty' };

  const tokens = raw.split(/\s+/);
  const { spec, verbIndex } = findVerb(tokens);

  // ── No verb: treat the whole input as a species name. ───────────────────
  // This is the commonest thing a researcher types, so it must not need a verb
  // and must not reach the model.
  if (!spec) {
    if (looksLikeQuestion(raw, tokens) || tokens.length > MAX_SPECIES_TOKENS) {
      // A sentence may still name a command longhand. Both halves must land —
      // an intent phrase and a species that resolves outright — or this falls
      // through to the agent untouched.
      const intent = matchIntent(raw);
      if (intent) {
        const remainder = stripScaffolding(raw);
        if (remainder) {
          const guess = resolveSpeciesArg(remainder, options.resolver);
          if (guess.ok) {
            const intentSpec = lookup(intent.verb);
            if (intentSpec) {
              return {
                kind: 'command',
                spec: intentSpec,
                species: [guess.value],
                values: { ...(intent.values ?? {}) },
                unavailable: intentSpec.unavailable,
              };
            }
          }
        }
      }
      return { kind: 'fallback', reason: 'unknown-intent', text: raw };
    }
    const attempt = resolveSpeciesArg(raw, options.resolver);
    if (attempt.ok) {
      const profile = lookup('species')!;
      return { kind: 'command', spec: profile, species: [attempt.value], values: {} };
    }
    if (attempt.resolution.status === 'ambiguous') {
      return {
        kind: 'disambiguate',
        spec: null,
        argName: 'species',
        input: raw,
        resolution: attempt.resolution,
      };
    }
    // Not a command, not a species: genuinely open-ended.
    return { kind: 'fallback', reason: 'unknown-intent', text: raw };
  }

  const argTokens = stripNoise(tokens.slice(verbIndex + 1));

  // ── Explicit agent hand-off. ────────────────────────────────────────────
  if (spec.verb === 'ask') {
    const question = tokens.slice(verbIndex + 1).join(' ').trim();
    if (!question) return { kind: 'fallback', reason: 'unknown-intent', text: raw };
    return { kind: 'fallback', reason: 'explicit', text: question };
  }

  if (spec.verb === 'help') {
    return { kind: 'command', spec, species: [], values: argTokens.length ? { command: argTokens[0] } : {} };
  }

  const speciesArgs = spec.args.filter(a => a.type === 'species');

  // ── Two-species commands. ───────────────────────────────────────────────
  if (speciesArgs.length === 2) {
    const halves = argTokens.join(' ').split(PAIR_SEPARATOR);
    if (halves.length !== 2 || !halves[0].trim() || !halves[1].trim()) {
      return { kind: 'fallback', reason: 'unresolved-species', text: raw };
    }
    const resolved: ResolvedSpecies[] = [];
    for (let i = 0; i < 2; i++) {
      const attempt = resolveSpeciesArg(halves[i].trim(), options.resolver);
      if (!attempt.ok) {
        if (attempt.resolution.status === 'ambiguous') {
          return {
            kind: 'disambiguate',
            spec,
            argName: speciesArgs[i].name,
            input: halves[i].trim(),
            resolution: attempt.resolution,
          };
        }
        return { kind: 'fallback', reason: 'unresolved-species', text: raw };
      }
      resolved.push(attempt.value);
    }
    return { kind: 'command', spec, species: resolved, values: {}, unavailable: spec.unavailable };
  }

  const { values, rest } = extractTrailingValues(argTokens, spec.args, options.regions);

  // ── Commands with no species argument. ──────────────────────────────────
  if (speciesArgs.length === 0) {
    const missing = spec.args.find(a => a.required && !(a.name in values));
    if (missing) {
      // A required region that was not recognised: try the remaining tokens
      // verbatim rather than failing, since the region list may be partial.
      if (missing.type === 'region' && rest.length) {
        values[missing.name] = rest.join(' ');
      } else {
        return { kind: 'fallback', reason: 'unknown-intent', text: raw };
      }
    }
    return { kind: 'command', spec, species: [], values, unavailable: spec.unavailable };
  }

  // ── Single-species commands. ────────────────────────────────────────────
  const phrase = rest.join(' ').trim();
  if (!phrase) {
    return { kind: 'fallback', reason: 'unresolved-species', text: raw };
  }

  const attempt = resolveSpeciesArg(phrase, options.resolver);
  if (!attempt.ok) {
    if (attempt.resolution.status === 'ambiguous') {
      return {
        kind: 'disambiguate',
        spec,
        argName: 'species',
        input: phrase,
        resolution: attempt.resolution,
      };
    }
    // The verb was clear but the bird was not. The agent cannot resolve a name
    // the local index rejected, so this is a dead end, not a fallback —
    // callers surface "no such species" rather than spending a model call.
    return { kind: 'fallback', reason: 'unresolved-species', text: raw };
  }

  // A required region that was not matched from the closed list.
  const regionArg = spec.args.find(a => a.type === 'region' && a.required);
  if (regionArg && !(regionArg.name in values)) {
    return { kind: 'fallback', reason: 'unknown-intent', text: raw };
  }

  return {
    kind: 'command',
    spec,
    species: [attempt.value],
    values,
    unavailable: spec.unavailable,
  };
}
