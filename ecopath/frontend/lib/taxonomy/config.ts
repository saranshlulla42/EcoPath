/**
 * Resolution thresholds.
 *
 * Both must be cleared to auto-resolve. The floor alone is not enough: a
 * partial query like "godwit" scores ~1.0 against BOTH Bar-tailed and
 * Black-tailed Godwit, and picking either would be a coin flip presented as an
 * answer. The margin is what turns that into a disambiguation prompt.
 */

/** Minimum confidence for the top candidate. */
export const CONFIDENCE_FLOOR = 0.9;

/** Minimum separation between the top candidate and the runner-up. */
export const CONFIDENCE_MARGIN = 0.05;

/** Candidates below this are not worth showing at all. */
export const CANDIDATE_FLOOR = 0.55;

/** How many candidates a disambiguation list may contain. */
export const MAX_CANDIDATES = 8;
