import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';
import { buildAliasTable, type EbirdTaxonRow } from '../lib/taxonomy/aliases';
import { createResolver } from '../lib/taxonomy/resolver';
import { parse } from '../lib/commands/parse';

/**
 * What fraction of queries the bar answers without the agent.
 *
 * Measured against two mixes, because the answer depends entirely on what
 * people type and a single flattering set would prove nothing:
 *
 *  - AGENT_STYLE: the twenty questions written for the chat agent in stage 1.
 *    These were composed as prose for a language model, so they are the
 *    pessimistic case — the bar was not designed for them.
 *  - BAR_STYLE: what a researcher types into a command bar once they know it
 *    exists. Terse, entity-first.
 *
 * Both are synthetic. Real traffic is what the telemetry module records in the
 * running app; these numbers bound the expectation, they do not replace it.
 */

const ARTIFACT = join(__dirname, '..', 'public', 'taxonomy', 'ebird-taxonomy.json');
const rows: EbirdTaxonRow[] = existsSync(ARTIFACT)
  ? JSON.parse(readFileSync(ARTIFACT, 'utf8'))
  : [];
const real = rows.length > 1000;

const REGIONS = new Set([
  'gujarat', 'kerala', 'assam', 'tamil nadu', 'rajasthan', 'karnataka',
  'maharashtra', 'delhi', 'odisha', 'punjab',
]);

/** The stage-1 replay set, verbatim. */
const AGENT_STYLE = [
  'Which bird species in the dataset are critically endangered?',
  'What data do you actually have — how many species, which years, which states?',
  'How have Sarus Crane numbers changed over time?',
  'Show me population trends for the Great Indian Bustard between 2015 and 2024.',
  'Are there any unusual population drops in Kerala?',
  'Which states have the most bird observations?',
  'Compare the Greater Flamingo and the Lesser Flamingo.',
  'Does rainfall affect Bar-headed Goose numbers in Gujarat?',
  'What migration routes do you have for the Amur Falcon?',
  'How many species are there in each IUCN category, counting only ones with population records?',
  'Is the Forest Owlet actually rare, or do you just not have much data on it?',
  'How is the Great Indian Bustard doing?',
  'Where is it found?',
  'Compare that with the Bengal Florican.',
  'Show me anomalies in Assam.',
  'What about Kerala?',
  'Which species drove those?',
  'Which states have the most threatened species?',
  'Focus on Gujarat.',
  'Show me the trend there since 2018.',
];

/** What the bar is actually for. */
const BAR_STYLE = [
  'bar-tailed godwit',
  'migration amur falcon',
  'migration house sparrow',
  'status sarus crane',
  'status forest owlet',
  'range greater flamingo january',
  'range indian pitta',
  'chart house sparrow',
  'chart indian vulture anomalies',
  'compare greater flamingo and lesser flamingo',
  'species peregrine falcon',
  'anomalies indian vulture gujarat',
  'weather bar-headed goose gujarat',
  'region kerala',
  'list CR',
  'help',
  'arcter',
  'blak-tailed godwit',
  'show me the migration of the amur falcon',
  'why do godwits fly nonstop over the Pacific?',
];

describe.skipIf(!real)('fraction served without the agent', () => {
  const resolver = createResolver(buildAliasTable(rows));
  const opts = { resolver, regions: REGIONS };

  function measure(label: string, queries: string[]) {
    const counts = { command: 0, disambiguate: 0, fallback: 0, empty: 0 };
    const fellBack: string[] = [];
    for (const q of queries) {
      const r = parse(q, opts);
      counts[r.kind] += 1;
      if (r.kind === 'fallback') fellBack.push(q);
    }
    // Only `fallback` reaches the agent. A disambiguation prompt is answered
    // locally from the Stage 3 index and costs nothing.
    const withoutAgent = queries.length - counts.fallback;
    console.log(
      `  ${label}: ${withoutAgent}/${queries.length} = ` +
        `${((withoutAgent / queries.length) * 100).toFixed(0)}% without the agent  ` +
        `(command ${counts.command}, disambiguate ${counts.disambiguate}, fallback ${counts.fallback})`,
    );
    for (const q of fellBack) console.log(`      -> agent: ${q}`);
    return { counts, withoutAgent, total: queries.length };
  }

  it('measures the agent-style mix', () => {
    const r = measure('agent-style (stage 1 replay set)', AGENT_STYLE);
    // No assertion on the rate: this mix was written for a model, and the point
    // is to report it honestly, not to hit a target.
    expect(r.total).toBe(20);
  });

  it('measures the command-bar mix', () => {
    const r = measure('bar-style', BAR_STYLE);
    // The one genuinely open question is the only thing that should escape.
    expect(r.counts.fallback).toBeLessThanOrEqual(2);
    expect(r.withoutAgent / r.total).toBeGreaterThanOrEqual(0.9);
  });

  it('never sends a resolvable species to the agent', () => {
    for (const q of ['migration amur falcon', 'arcter', 'status sarus crane']) {
      expect(parse(q, opts).kind, q).toBe('command');
    }
  });
});
