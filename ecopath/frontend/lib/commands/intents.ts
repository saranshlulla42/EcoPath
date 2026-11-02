/**
 * Phrasings that name a command without using its verb.
 *
 * "What migration routes do you have for the Amur Falcon?" is not an
 * open-ended question — it is `migration amur falcon` written out longhand, and
 * sending it to a language model is a wasted call and a slower answer.
 *
 * These are regexes, not a model: the parse stays deterministic and auditable.
 * The rule that keeps them safe is that a pattern alone is never enough. A
 * phrase only becomes a command when an intent keyword AND a confidently
 * resolved species are both present; if either is missing the input falls
 * through to the agent unchanged. A wrong deterministic answer is worse than a
 * fallback, because the user is never told a guess was made.
 */

export interface IntentPattern {
  verb: string;
  pattern: RegExp;
  /** Set when the phrasing also implies an argument, e.g. "anomalies". */
  values?: Record<string, string | number>;
}

export const INTENT_PATTERNS: IntentPattern[] = [
  // Migration, flyways, seasonal movement.
  { verb: 'migration', pattern: /\b(migrat\w+|flyway|corridor|winter\w*\s+range)\b/i },

  // Anomalies. Checked before the population patterns, since "unusual drop in
  // numbers" contains both and the anomaly reading is the specific one.
  {
    verb: 'anomalies',
    pattern: /\b(anomal\w+|unusual\s+\w*\s*(drop|decline|spike|surge)|sudden\s+(drop|decline))\b/i,
  },

  // Population over time.
  {
    verb: 'chart',
    pattern: /\b(population|numbers|trend\w*|over\s+time|declin\w+|increas\w+)\b/i,
    values: { metric: 'observations' },
  },

  // Whether the data supports any claim at all.
  {
    verb: 'status',
    pattern: /\b(is\s+it\s+migratory|resident\s+or\s+migratory|enough\s+data|much\s+data|actually\s+rare)\b/i,
  },

  // Where a bird occurs.
  { verb: 'range', pattern: /\b(where\s+is|where\s+are|found\s+in|distribut\w+|occurs?\s+in)\b/i },
];

/**
 * The first intent whose pattern the text matches, or null.
 *
 * Order is significance, not preference: the most specific reading wins, so an
 * "unusual drop in numbers" resolves to anomalies rather than a plain chart.
 */
export function matchIntent(text: string): IntentPattern | null {
  for (const intent of INTENT_PATTERNS) {
    if (intent.pattern.test(text)) return intent;
  }
  return null;
}

/**
 * Strip the words that carry the intent, leaving what should be the species.
 *
 * Without this the species resolver is handed a whole sentence and either
 * fails or matches something absurd on a stray token.
 */
const SCAFFOLDING = new RegExp(
  String.raw`\b(what|which|how|where|when|why|who|do|does|did|is|are|was|were|has|have|had|` +
    String.raw`can|could|should|would|will|show|tell|give|find|the|a|an|of|for|in|on|to|me|us|you|` +
    String.raw`your|any|some|there|here|about|please|numbers?|population|populations|trend|trends|` +
    String.raw`data|records?|routes?|migration|migratory|migrate[sd]?|flyway|corridors?|anomal\w+|` +
    String.raw`over|time|years?|changed?|change|declin\w+|increas\w+|distribut\w+|found|occurs?|` +
    String.raw`rare|much|enough|actually|just|or|and|not|it|its|been|doing)\b`,
  'gi',
);

export function stripScaffolding(text: string): string {
  return text
    .replace(/[?.!,;:]/g, ' ')
    .replace(SCAFFOLDING, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}
