/**
 * eBird service.
 *
 * The eBird API is now reached through the backend's /api/data/ebird/* routes.
 * This module previously called api.ebird.org from the browser with the key in
 * NEXT_PUBLIC_EBIRD_API_KEY, which shipped it to every visitor; the multi-region
 * fan-out, retries and deduplication now happen server-side, where the results
 * are also cached across users instead of per tab.
 */

import type { EBirdObservation, MigrationSpeciesInfo } from "./types";
import {
  getEBirdObservations,
  getEBirdSeasonal,
  getEBirdTaxonomy,
  type UnifiedObservation,
} from "./dataClient";

/** Map the backend's normalised observation onto the shape the UI expects. */
export function normalizeObservation(raw: UnifiedObservation): EBirdObservation {
  return {
    lat: raw.lat ?? 0,
    lng: raw.lng ?? 0,
    date: raw.date ?? "",
    count: raw.count ?? 1,
    speciesCode: raw.species_code ?? "",
    speciesName: raw.species_name ?? "Unknown",
    locationName: raw.location_name ?? "Unknown",
  };
}

/**
 * Recent observations for a species across the flyway regions.
 * `regionCode` is accepted for signature compatibility; the backend decides
 * which regions to span.
 */
export async function getRecentObservations(
  speciesCode: string,
  regionCode?: string,
  back: number = 30
): Promise<EBirdObservation[]> {
  const rows = await getEBirdObservations(speciesCode, back);
  return rows.map(normalizeObservation);
}

/** Observations bucketed by ISO week for a given year. */
export async function getSeasonalObservations(
  speciesCode: string,
  year: number
): Promise<Map<number, EBirdObservation[]>> {
  const byWeek = await getEBirdSeasonal(speciesCode, year);
  const result = new Map<number, EBirdObservation[]>();
  for (const [week, observations] of Object.entries(byWeek ?? {})) {
    result.set(Number(week), (observations ?? []).map(normalizeObservation));
  }
  return result;
}

// Orders that contain the long-distance migrants the migration view cares about.
const MIGRATORY_ORDERS = [
  "Charadriiformes", "Anseriformes", "Accipitriformes", "Falconiformes",
  "Gruiformes", "Ciconiiformes", "Gaviiformes", "Podicipediformes",
  "Procellariiformes", "Pelecaniformes", "Coraciiformes", "Cuculiformes",
  "Passeriformes",
];

const SPECIES_COLORS = [
  "#06b6d4", "#f59e0b", "#10b981", "#8b5cf6",
  "#f43f5e", "#3b82f6", "#ec4899", "#14b8a6",
];

/**
 * Migratory species from the eBird taxonomy.
 *
 * Still cached in sessionStorage: the backend caches the upstream call, but
 * this avoids re-transferring a large list on every page view.
 */
export async function getMigratoryTaxonomy(): Promise<MigrationSpeciesInfo[]> {
  const CACHE_KEY = "ebird-taxonomy-v3";
  if (typeof sessionStorage !== "undefined") {
    try {
      const cached = sessionStorage.getItem(CACHE_KEY);
      if (cached) {
        const parsed = JSON.parse(cached) as MigrationSpeciesInfo[];
        if (Array.isArray(parsed) && parsed.length > 100) return parsed;
        sessionStorage.removeItem(CACHE_KEY);
      }
    } catch {
      sessionStorage.removeItem(CACHE_KEY);
    }
  }

  const taxonomy = await getEBirdTaxonomy(MIGRATORY_ORDERS);

  let colorIdx = 0;
  const migratory: MigrationSpeciesInfo[] = (taxonomy ?? []).map((t) => ({
    speciesCode: t.species_code,
    commonName: t.common_name,
    scientificName: t.scientific_name,
    dataSource: "ebird" as const,
    color: SPECIES_COLORS[colorIdx++ % SPECIES_COLORS.length],
  }));

  if (typeof sessionStorage !== "undefined" && migratory.length > 0) {
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify(migratory));
    } catch (e) {
      console.warn("[ebird] sessionStorage cache failed (likely quota):", e);
    }
  }

  return migratory;
}
