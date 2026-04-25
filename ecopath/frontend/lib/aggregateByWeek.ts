import type { EBirdObservation } from "./types";

/**
 * Aggregate a flat array of normalised observations into ISO weeks (1–52).
 *
 * Uses the ISO week number algorithm: the week containing the first Thursday
 * of January is week 1.
 *
 * Returns a Map<weekNumber, EBirdObservation[]> where weekNumber ∈ [1, 52].
 * Observations from week 53 (rare, leap years) are folded into week 52.
 */
export function aggregateByWeek(
  observations: EBirdObservation[]
): Map<number, EBirdObservation[]> {
  const weekMap = new Map<number, EBirdObservation[]>();

  // Initialize all 52 weeks
  for (let w = 1; w <= 52; w++) {
    weekMap.set(w, []);
  }

  for (const obs of observations) {
    if (!obs.date) continue;

    const date = new Date(obs.date);
    if (isNaN(date.getTime())) continue;

    let week = getISOWeekNumber(date);

    // Fold week 53 into week 52
    if (week > 52) week = 52;
    // Clamp to valid range
    if (week < 1) week = 1;

    weekMap.get(week)!.push(obs);
  }

  return weekMap;
}

/**
 * Compute the ISO 8601 week number for a given date.
 *
 * The ISO week starts on Monday. Week 1 is the week containing
 * the first Thursday of the year.
 */
export function getISOWeekNumber(date: Date): number {
  const d = new Date(
    Date.UTC(date.getFullYear(), date.getMonth(), date.getDate())
  );
  // Set to nearest Thursday: current date + 4 - day number (Monday = 1, Sunday = 7)
  const dayNum = d.getUTCDay() || 7; // Sunday = 7
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  // Get first day of year
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  // Calculate week number
  const weekNo = Math.ceil(
    ((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7
  );
  return weekNo;
}
