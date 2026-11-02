/**
 * The closed command registry.
 *
 * Closed is the point: every verb here is something the app can answer from its
 * own data. Anything outside this set is an open-ended question and goes to the
 * agent. That boundary is what keeps the common case free of model calls —
 * "migration bar-tailed godwit" is a lookup, not a conversation.
 *
 * Arguments are typed so the parser can validate before executing. A `species`
 * argument is never a string downstream: it resolves through the Stage 3 index
 * to a canonical taxon id, or the command does not run.
 */

export type ArgType = 'species' | 'region' | 'metric' | 'month' | 'iucn' | 'text';

export interface ArgSpec {
  name: string;
  type: ArgType;
  required: boolean;
  /** Allowed values for enum-ish types; first is the default. */
  values?: string[];
  description: string;
}

export interface CommandSpec {
  verb: string;
  aliases: string[];
  args: ArgSpec[];
  summary: string;
  /** Example the help panel shows. */
  example: string;
  /**
   * Whether this command depends on a database function that has not been
   * applied yet. Such commands still parse and still avoid the LLM; they return
   * a clear unavailable message rather than failing obscurely.
   */
  unavailable?: string;
}

export const METRICS = ['observations', 'anomalies'] as const;
export const TOP_METRICS = ['species', 'observations', 'threatened'] as const;
export const IUCN = ['LC', 'NT', 'VU', 'EN', 'CR', 'DD'] as const;

const SPECIES_ARG: ArgSpec = {
  name: 'species',
  type: 'species',
  required: true,
  description: 'A species name, code, or partial name',
};

export const COMMANDS: CommandSpec[] = [
  {
    verb: 'species',
    aliases: ['sp', 'info', 'profile'],
    args: [SPECIES_ARG],
    summary: 'Species profile: status, habitat, range, records',
    example: 'species bar-tailed godwit',
  },
  {
    verb: 'migration',
    aliases: ['migrate', 'migratory', 'corridor', 'corridors'],
    args: [SPECIES_ARG],
    summary: 'Migration track across the year, if the species has one',
    example: 'migration amur falcon',
  },
  {
    verb: 'range',
    aliases: ['map', 'where', 'distribution'],
    args: [
      SPECIES_ARG,
      { name: 'month', type: 'month', required: false, description: 'Month 1-12, or a month name' },
    ],
    summary: 'Observation-density map, optionally for one month',
    example: 'range greater flamingo january',
  },
  {
    verb: 'chart',
    aliases: ['trend', 'graph', 'plot'],
    args: [
      SPECIES_ARG,
      {
        name: 'metric',
        type: 'metric',
        required: false,
        values: [...METRICS],
        description: 'What to plot',
      },
    ],
    summary: 'Time series of observations or anomalies',
    example: 'chart house sparrow observations',
  },
  {
    verb: 'status',
    aliases: ['migratory?', 'resident?'],
    args: [SPECIES_ARG],
    summary: 'Migratory / resident / insufficient data, with the evidence',
    example: 'status sarus crane',
  },
  {
    verb: 'anomalies',
    aliases: ['anomaly', 'unusual', 'outliers'],
    args: [
      SPECIES_ARG,
      { name: 'region', type: 'region', required: false, description: 'An Indian state' },
    ],
    summary: 'Detected population anomalies',
    example: 'anomalies indian vulture gujarat',
  },
  {
    verb: 'compare',
    aliases: ['vs', 'versus'],
    args: [
      { ...SPECIES_ARG, name: 'speciesA' },
      { ...SPECIES_ARG, name: 'speciesB' },
    ],
    summary: 'Two species side by side',
    example: 'compare greater flamingo and lesser flamingo',
  },
  {
    verb: 'weather',
    aliases: ['climate', 'rainfall'],
    args: [
      SPECIES_ARG,
      { name: 'region', type: 'region', required: true, description: 'An Indian state' },
    ],
    summary: 'Observations against temperature and rainfall',
    example: 'weather bar-headed goose gujarat',
  },
  {
    verb: 'region',
    aliases: ['state', 'in'],
    args: [{ name: 'region', type: 'region', required: true, description: 'An Indian state' }],
    summary: 'What the dataset holds for one state',
    example: 'region kerala',
  },
  {
    verb: 'top',
    aliases: ['rank', 'ranking', 'most'],
    args: [
      {
        name: 'metric',
        type: 'metric',
        required: false,
        values: [...TOP_METRICS],
        description: 'What to rank states by',
      },
    ],
    summary: 'States ranked by richness, observations or threatened species',
    example: 'top threatened',
    unavailable: 'The rank_states database function has not been applied yet.',
  },
  {
    verb: 'list',
    aliases: ['ls', 'find', 'catalogue'],
    args: [
      { name: 'iucn', type: 'iucn', required: false, values: [...IUCN], description: 'IUCN category' },
      { name: 'region', type: 'region', required: false, description: 'An Indian state' },
    ],
    summary: 'Species in the catalogue, filtered',
    example: 'list CR',
  },
  {
    verb: 'dataset',
    aliases: ['coverage', 'holdings'],
    args: [],
    summary: 'What EcoPath actually holds',
    example: 'dataset',
    unavailable: 'The dataset_coverage database function has not been applied yet.',
  },
  {
    verb: 'help',
    aliases: ['?', 'commands'],
    args: [{ name: 'command', type: 'text', required: false, description: 'A command name' }],
    summary: 'List commands',
    example: 'help migration',
  },
  {
    verb: 'ask',
    // No natural-language question words here. Making "why" an alias would
    // route every open question through the *explicit* path and hide, in the
    // telemetry, how often the parser genuinely failed to understand.
    aliases: [],
    args: [{ name: 'question', type: 'text', required: true, description: 'A free-form question' }],
    summary: 'Ask the research agent anything the commands do not cover',
    example: 'ask why do godwits fly nonstop over the Pacific',
  },
];

/** verb or alias -> spec. Built once; aliases may not collide. */
export const BY_VERB: Map<string, CommandSpec> = (() => {
  const map = new Map<string, CommandSpec>();
  for (const spec of COMMANDS) {
    for (const key of [spec.verb, ...spec.aliases]) {
      if (map.has(key)) {
        throw new Error(`duplicate command key "${key}"`);
      }
      map.set(key, spec);
    }
  }
  return map;
})();

/** Commands that hand off to the model rather than answering locally. */
export const LLM_VERBS = new Set(['ask']);

export function lookup(token: string): CommandSpec | undefined {
  return BY_VERB.get(token.toLowerCase());
}
