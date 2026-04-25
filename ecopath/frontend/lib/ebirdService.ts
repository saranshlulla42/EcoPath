import axios from "axios";
import type { EBirdObservation, MigrationSpeciesInfo } from "./types";

// ── eBird API v2 Service ───────────────────────────────────────────────────
// Docs: https://documenter.getpostman.com/view/664302/S1ENwy59

const EBIRD_BASE = "https://api.ebird.org/v2";
const EBIRD_API_KEY = process.env.NEXT_PUBLIC_EBIRD_API_KEY ?? "";

const ebirdClient = axios.create({
  baseURL: EBIRD_BASE,
  timeout: 15000,
  headers: { "X-eBirdApiToken": EBIRD_API_KEY },
});

interface RawEBirdObservation {
  lat?: number;
  lng?: number;
  obsDt?: string;
  howMany?: number;
  howManyStr?: string;
  speciesCode?: string;
  comName?: string;
  sciName?: string;
  locName?: string;
}

interface RawTaxonomyItem {
  category?: string;
  order?: string;
  speciesCode: string;
  comName: string;
  sciName: string;
}

// ── Normalisation ──────────────────────────────────────────────────────────

/** Convert a raw eBird observation to a normalised internal shape */
export function normalizeObservation(raw: RawEBirdObservation): EBirdObservation {
  const parsedHowMany =
    typeof raw.howManyStr === "string"
      ? Number.parseFloat(raw.howManyStr.replace(/,/g, ""))
      : Number.NaN;

  return {
    lat: raw.lat ?? 0,
    lng: raw.lng ?? 0,
    date: raw.obsDt ?? "",
    count:
      typeof raw.howMany === "number"
        ? raw.howMany
        : Number.isFinite(parsedHowMany)
        ? parsedHowMany
        : 1,
    speciesCode: raw.speciesCode ?? "",
    speciesName: raw.comName ?? raw.sciName ?? "Unknown",
    locationName: raw.locName ?? "Unknown",
  };
}

// ── API Methods ────────────────────────────────────────────────────────────

/**
 * Fetch recent observations for a species in a region.
 * Maps to GET /data/obs/{regionCode}/recent/{speciesCode}
 */
export async function getRecentObservations(
  speciesCode: string,
  regionCode: string, // parameter kept for signature compatibility
  back: number = 30
): Promise<EBirdObservation[]> {
  const GLOBAL_REGIONS = [
    'US', 'CA', 'MX',           // North America
    'BR', 'AR', 'CO', 'PE',     // South America
    'GB', 'DE', 'FR', 'SE', 'NO', 'FI', 'RU', // Europe + Russia
    'NG', 'KE', 'ZA', 'ET', 'TZ', 'GH',       // Africa
    'IN', 'CN', 'JP', 'AU', 'NZ', 'ID',        // Asia-Pacific
    'EG', 'SA', 'IR'                            // Middle East
  ];

  const results = await Promise.allSettled(
    GLOBAL_REGIONS.map((region) =>
      ebirdClient.get<RawEBirdObservation[]>(`/data/obs/${region}/recent/${speciesCode}`, {
        params: { back },
      })
    )
  );

  const flatObs: RawEBirdObservation[] = [];
  for (const res of results) {
    if (res.status === "fulfilled" && Array.isArray(res.value.data)) {
      flatObs.push(...res.value.data);
    }
  }

  // Deduplicate by composite key: ${speciesCode}_${lat}_${lng}_${obsDt}
  const seen = new Set<string>();
  const uniqueObs: RawEBirdObservation[] = [];
  for (const obs of flatObs) {
    const key = `${obs.speciesCode}_${obs.lat}_${obs.lng}_${obs.obsDt}`;
    if (!seen.has(key)) {
      seen.add(key);
      uniqueObs.push(obs);
    }
  }

  return uniqueObs.map(normalizeObservation);
}

/**
 * Fetch observations across all weeks of a given year by batching weekly requests.
 * Returns a Map of ISO week number → observation array.
 *
 * Limits concurrency to 5 simultaneous requests to avoid eBird rate limits.
 */
export async function getSeasonalObservations(
  speciesCode: string,
  year: number
): Promise<Map<number, EBirdObservation[]>> {
  const weekMap = new Map<number, EBirdObservation[]>();

  // Build 52 date ranges (ISO weeks)
  const weekRanges: { week: number; startDate: string }[] = [];
  for (let w = 1; w <= 52; w++) {
    // ISO week → approximate start date
    const jan1 = new Date(year, 0, 1);
    const dayOffset = (w - 1) * 7;
    const weekStart = new Date(jan1.getTime() + dayOffset * 86400000);
    const yyyy = weekStart.getFullYear();
    const mm = String(weekStart.getMonth() + 1).padStart(2, "0");
    const dd = String(weekStart.getDate()).padStart(2, "0");
    weekRanges.push({ week: w, startDate: `${yyyy}-${mm}-${dd}` });
  }

  // Concurrent fetcher with concurrency limit
  const CONCURRENCY = 5;
  for (let i = 0; i < weekRanges.length; i += CONCURRENCY) {
    const batch = weekRanges.slice(i, i + CONCURRENCY);
    const results = await Promise.allSettled(
      batch.map(async ({ week, startDate }) => {
        try {
          // Use historic observations endpoint with date range
          const resp = await ebirdClient.get<RawEBirdObservation[]>(
            `/data/obs/world/historic/${startDate}`,
            {
              params: { species: speciesCode, maxResults: 100 },
            }
          );
          return {
            week,
            observations: (resp.data ?? []).map(normalizeObservation),
          };
        } catch {
          return { week, observations: [] as EBirdObservation[] };
        }
      })
    );

    for (const result of results) {
      if (result.status === "fulfilled") {
        weekMap.set(result.value.week, result.value.observations);
      }
    }
  }

  return weekMap;
}

/**
 * Fetch all species observed in a region.
 * Maps to GET /product/spplist/{regionCode}
 */
export async function getSpeciesList(regionCode: string): Promise<string[]> {
  const resp = await ebirdClient.get(`/product/spplist/${regionCode}`);
  return resp.data ?? [];
}

/**
 * Fetch and filter eBird taxonomy for migratory species.
 * Fetches once and caches in sessionStorage.
 */
export async function getMigratoryTaxonomy(): Promise<MigrationSpeciesInfo[]> {
  const CACHE_KEY = "ebird-taxonomy-v2";
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

  const resp = await ebirdClient.get<RawTaxonomyItem[]>("/ref/taxonomy/ebird?fmt=json");
  const taxonomy = resp.data ?? [];
  console.log("[ebird] taxonomy items fetched:", taxonomy.length);

  const MIGRATORY_ORDERS = new Set([
    "Charadriiformes",
    "Anseriformes",
    "Accipitriformes",
    "Falconiformes",
    "Gruiformes",
    "Ciconiiformes",
    "Gaviiformes",
    "Podicipediformes",
    "Procellariiformes",
    "Pelecaniformes",
    "Coraciiformes",
    "Cuculiformes",
    "Passeriformes",
  ]);

  const SPECIES_COLORS = [
    "#06b6d4", "#f59e0b", "#10b981", "#8b5cf6",
    "#f43f5e", "#3b82f6", "#ec4899", "#14b8a6"
  ];

  let colorIdx = 0;
  const migratory = taxonomy
    .filter((t) => t.category === "species" && !!t.order && MIGRATORY_ORDERS.has(t.order))
    .map((t) => ({
      speciesCode: t.speciesCode,
      commonName: t.comName,
      scientificName: t.sciName,
      dataSource: "ebird" as const,
      color: SPECIES_COLORS[colorIdx++ % SPECIES_COLORS.length],
    }));

  console.log("[ebird] migratory species after filter:", migratory.length);
  if (typeof sessionStorage !== "undefined" && migratory.length > 0) {
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify(migratory));
    } catch (e) {
      console.warn("[ebird] sessionStorage cache failed (likely quota):", e);
    }
  }

  return migratory;
}
