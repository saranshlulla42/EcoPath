/**
 * Query and alias normalisation.
 *
 * Everything compared during resolution passes through here, so "Bar-tailed
 * Godwit", "bar tailed godwit" and "BAR-TAILED  GODWIT" are one string.
 */

/**
 * Spelling variants that genuinely occur in bird common names. Kept short and
 * explicit rather than general: a broad transliteration table would start
 * collapsing distinct species names into each other, which is the one failure
 * mode this whole module exists to prevent.
 */
const VARIANTS: ReadonlyArray<readonly [RegExp, string]> = [
  [/\bgrey\b/g, 'gray'],
  [/\bmoustached\b/g, 'mustached'],
  [/\bcoloured\b/g, 'colored'],
  [/\bhawaiian\b/g, 'hawaian'],
];

/** Lowercase, strip diacritics and punctuation, collapse whitespace. */
export function normalize(input: string): string {
  let s = (input ?? '')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
  for (const [pattern, replacement] of VARIANTS) s = s.replace(pattern, replacement);
  return s;
}

/** Normalised with all separators removed — "bartailedgodwit". */
export function compact(input: string): string {
  return normalize(input).replace(/ /g, '');
}

export function tokens(input: string): string[] {
  const n = normalize(input);
  return n ? n.split(' ') : [];
}

/**
 * Index of each character of `compact(name)` back to whether it begins a token.
 * Used by the subsequence scorer to reward matches at word starts.
 */
export function tokenStartFlags(input: string): boolean[] {
  const flags: boolean[] = [];
  for (const token of tokens(input)) {
    for (let i = 0; i < token.length; i++) flags.push(i === 0);
  }
  return flags;
}
